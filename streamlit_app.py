import streamlit as st
import pandas as pd
from typing import Any, Dict

from core.data_io import load_data, clean_data
from core import scoring


@st.cache_data
def load_prepared_data() -> pd.DataFrame:
    """
    Load, clean, and enrich the laptop dataset with score columns.
    """
    df = load_data(use_cache=True)
    if df is None or df.empty:
        return pd.DataFrame()

    df = clean_data(df)

    if "cpu" in df.columns:
        df["cpu_score"] = df["cpu"].apply(scoring.get_cpu_score)
    else:
        df["cpu_score"] = 5.0

    if "gpu" in df.columns:
        df["gpu_norm"] = df["gpu"].apply(scoring.normalize_gpu_model)
        df["gpu_score"] = df["gpu_norm"].apply(scoring.get_gpu_score)
    else:
        df["gpu_score"] = 3.0
        df["gpu_norm"] = "Integrated (generic)"

    return df


def build_preferences(df: pd.DataFrame) -> Dict[str, Any] | None:
    """
    Collect user preferences from the sidebar.
    """
    preferences: Dict[str, Any] = {}

    # Ported from main_recommender.py: persist extra usage details across reruns
    st.session_state.setdefault("design_profiles", ["graphic"])
    st.session_state.setdefault("productivity_profile", "office")

    if "price" not in df.columns or df["price"].isna().all():
        st.error("'price' kolonu bulunamad\u0131 veya bo\u015f.")
        return None

    min_price = int(df["price"].min())
    max_price = int(df["price"].max())
    default_upper = max(min_price, min_price + (max_price - min_price) // 3)
    min_budget, max_budget = st.sidebar.slider(
        "\U0001F4B0 B\u00fct\u00e7e aral\u0131\u011f\u0131 (TL)",
        min_value=min_price,
        max_value=max_price,
        value=(min_price, default_upper),
        step=1000,
    )
    preferences["min_budget"] = min_budget
    preferences["max_budget"] = max_budget

    usage_fallback = {
        "gaming": "\U0001F3AE Oyun",
        "portability": "\U0001F9F3 Ta\u015f\u0131nabilirlik",
        "productivity": "\U0001F4C8 \u00dcretkenlik",
        "design": "\U0001F3A8 Tasar\u0131m",
        "dev": "\U0001F4BB Yaz\u0131l\u0131m Geli\u015ftirme",
    }
    usage_choices = []
    for _, (usage_key, label) in sorted(scoring.USAGE_OPTIONS.items()):
        display = usage_fallback.get(usage_key, label)
        usage_choices.append((usage_key, display))

    usage_labels = [label for _, label in usage_choices]
    selected_usage_label = st.sidebar.selectbox(
        "\U0001F3AF Kullan\u0131m amac\u0131", options=usage_labels, index=0
    )
    usage_key = next(
        (key for key, lbl in usage_choices if lbl == selected_usage_label),
        usage_choices[0][0],
    )
    preferences["usage_key"] = usage_key
    preferences["usage_label"] = selected_usage_label

    if usage_key == "dev":
        dev_options = {
            "web": "\U0001F310 Web / Backend",
            "ml": "\U0001F4CA Veri / ML",
            "mobile": "\U0001F4F1 Mobil (Android/iOS)",
            "gamedev": "\U0001F3AE Oyun / 3D",
            "general": "\U0001F9F0 Genel CS",
        }
        dev_mode = st.sidebar.selectbox(
            "\U0001F6E0\ufe0f Geli\u015ftirici profili",
            options=list(dev_options.keys()),
            format_func=lambda k: dev_options[k],
        )
        preferences["dev_mode"] = dev_mode

    if usage_key == "productivity":
        prod_options = {
            "office": "Ofis i\u015fleri / dok\u00fcman",
            "data": "Veri yo\u011fun (Excel, raporlama)",
            "light_dev": "Hafif yaz\u0131l\u0131m geli\u015ftirme",
            "multitask": "\u00c7oklu g\u00f6rev (fazla pencere/monit\u00f6r)",
        }
        prod_default = st.session_state.get("productivity_profile", "office")
        prod_keys = list(prod_options.keys())
        selected_prod = st.sidebar.selectbox(
            "\U0001F4C8 \u00dcretkenlik profili",
            options=prod_keys,
            format_func=lambda k: prod_options[k],
            index=prod_keys.index(prod_default) if prod_default in prod_keys else 0,
        )
        st.session_state["productivity_profile"] = selected_prod
        preferences["productivity_profile"] = selected_prod  # ported from main_recommender.py

    if usage_key == "gaming":
        gaming_titles = list(scoring.GAMING_TITLE_SCORES.keys())
        selected_titles = st.sidebar.multiselect(
            "\U0001F3AE Oynamak istedi\u011fin oyunlar",
            options=gaming_titles,
            default=[],
        )
        if selected_titles:
            needed = max(scoring.GAMING_TITLE_SCORES[t] for t in selected_titles)
            preferences["gaming_titles"] = selected_titles
            preferences["min_gpu_score_required"] = max(6.0, needed)
        else:
            preferences["gaming_titles"] = []
            preferences["min_gpu_score_required"] = 6.0

    if usage_key == "design":
        design_options = {
            "graphic": "Grafik/foto\u011fraf (Photoshop, Illustrator, Figma)",
            "video": "Video/motion (Premiere, After Effects, DaVinci)",
            "3d": "3D modelleme/render (Blender, Maya, 3ds Max)",
            "cad": "Mimari/teknik \u00e7izim (AutoCAD, Revit, Solidworks)",
        }
        design_keys = list(design_options.keys())
        default_profiles = [
            p for p in st.session_state.get("design_profiles", ["graphic"]) if p in design_keys
        ] or ["graphic"]
        selected_profiles = st.sidebar.multiselect(
            "\U0001F3A8 Tasar\u0131m profili (birden fazla se\u00e7ilebilir)",
            options=design_keys,
            format_func=lambda k: design_options[k],
            default=default_profiles,
        )
        if not selected_profiles:
            selected_profiles = ["graphic"]
        st.session_state["design_profiles"] = selected_profiles

        if any(k in selected_profiles for k in ["3d"]):
            gpu_hint = "high"
        elif any(k in selected_profiles for k in ["video", "cad"]):
            gpu_hint = "mid"
        else:
            gpu_hint = "low"

        if any(k in selected_profiles for k in ["3d", "video", "cad"]):
            min_ram_hint = 32
        else:
            min_ram_hint = 16

        preferences["design_profiles"] = selected_profiles  # ported from main_recommender.py
        preferences["design_gpu_hint"] = gpu_hint  # ported from main_recommender.py
        preferences["design_min_ram_hint"] = min_ram_hint  # ported from main_recommender.py

    advanced = st.sidebar.checkbox("\U0001F4A1 Geli\u015fmi\u015f filtreler", value=False)
    if advanced:
        brand_options = sorted({str(b).lower() for b in df["brand"].dropna()})
        selected_brands = st.sidebar.multiselect(
            "Marka se\u00e7imi",
            options=brand_options,
            default=brand_options,
        )
        preferences["allowed_brands"] = selected_brands

        min_ram = st.sidebar.slider(
            "Minimum RAM (GB)",
            min_value=4,
            max_value=64,
            value=16,
            step=4,
        )
        preferences["min_ram"] = min_ram

        min_ssd = st.sidebar.slider(
            "Minimum SSD (GB)",
            min_value=128,
            max_value=2048,
            value=512,
            step=128,
        )
        preferences["min_ssd"] = min_ssd

        os_candidates = ["windows", "macos", "linux", "freedos"]
        available_oses = [
            os_name
            for os_name in os_candidates
            if os_name in set(df["os"].dropna().str.lower())
        ]
        selected_oses = st.sidebar.multiselect(
            "\u0130\u015fletim sistemi",
            options=available_oses,
            default=available_oses,
        )
        preferences["allowed_oses"] = selected_oses

        if usage_key == "gaming":
            exclude_apple = st.sidebar.checkbox(
                "\U0001F3AF Gaming'de Macbook'lar\u0131 gizle", value=False
            )
            preferences["exclude_apple_in_gaming"] = exclude_apple

    top_n = st.sidebar.slider(
        "Ka\u00e7 adet \u00f6neri g\u00f6sterilsin?", min_value=3, max_value=10, value=5, step=1
    )
    preferences["top_n"] = int(top_n)

    preferences["show_breakdown"] = st.sidebar.checkbox(
        "Skor detaylar\u0131n\u0131 g\u00f6ster (debug)", value=False
    )

    return preferences


def show_recommendations_streamlit(recs: pd.DataFrame, preferences: Dict[str, Any]) -> None:
    """
    Render recommendations as Streamlit cards.
    """
    if recs is None or recs.empty:
        st.warning("Bu filtrelerle \u00f6neri bulunamad\u0131.")
        return

    usage_label = recs.attrs.get("usage_label", preferences.get("usage_label", ""))
    avg_score = recs.attrs.get("avg_score", recs["score"].mean())
    price_min, price_max = recs.attrs.get(
        "price_range", (recs["price"].min(), recs["price"].max())
    )

    st.subheader("\U0001F3C6 \u00d6neriler")
    if usage_label:
        st.caption(usage_label)

    col_avg, col_price, col_count = st.columns(3)
    col_avg.metric("Ortalama skor", f"{avg_score:.1f}/100")
    col_price.metric("Fiyat aral\u0131\u011f\u0131", f"{price_min:,.0f} - {price_max:,.0f} TL")
    col_count.metric("\u00d6neri say\u0131s\u0131", str(len(recs)))

    for idx, (_, row) in enumerate(recs.iterrows(), start=1):
        with st.container():
            title = row.get("name", "(\u0130simsiz cihaz)")
            st.markdown(f"### {idx}. {title}")
            left, middle, right = st.columns([2, 2, 2])

            price_val = row.get("price")
            price_text = f"{price_val:,.0f} TL" if pd.notna(price_val) else "Bilinmiyor"
            score_val = row.get("score")
            score_text = f"{score_val:.1f}/100" if pd.notna(score_val) else "-"

            left.write(f"\U0001F4B8 Fiyat: {price_text}")
            left.write(f"\u2b50 Toplam skor: {score_text}")
            if preferences.get("show_breakdown") and row.get("score_breakdown"):
                left.caption(f"Skor detaylar\u0131: {row.get('score_breakdown')}")

            cpu_text = row.get("cpu", "Belirtilmedi")
            cpu_score = row.get("cpu_score", 0)
            gpu_text = row.get("gpu_norm", row.get("gpu", "Belirtilmedi"))
            gpu_score = row.get("gpu_score", 0)
            middle.write(f"\U0001F9E0 CPU: {cpu_text} (Skor: {cpu_score:.1f})")
            middle.write(f"\U0001F5A5\ufe0f GPU: {gpu_text} (Skor: {gpu_score:.1f})")

            ram_text = f"{row.get('ram_gb', 0):.0f} GB"
            ssd_text = f"{row.get('ssd_gb', 0):.0f} GB"
            screen_size = row.get("screen_size", None)
            screen_text = f'{screen_size:.1f}"' if pd.notna(screen_size) else "Belirtilmedi"
            os_text = row.get("os", "freedos")

            right.write(f"\U0001F9F4 RAM: {ram_text}")
            right.write(f"\U0001F4BE SSD: {ssd_text}")
            right.write(f"\U0001F4FA Ekran: {screen_text}")
            right.write(f"\U0001F5A5\ufe0f OS: {os_text}")

            url = row.get("url")
            if isinstance(url, str) and url.strip():
                right.link_button("\U0001F517 \u00dcr\u00fcn\u00fc a\u00e7", url)

        st.markdown("---")


def main():
    """
    Streamlit uygulamas\u0131n\u0131n giri\u015f noktas\u0131.
    """
    st.set_page_config(
        page_title="Laptop Recommender",
        page_icon="\U0001F4BB",
        layout="wide",
    )

    st.title("\U0001F4BB Laptop \u00d6neri Sistemi")
    st.write(
        "T\u00fcrkiye'deki pop\u00fcler ma\u011fazalardan toplanan verilerle, "
        "kullan\u0131m senaryona g\u00f6re en uygun laptoplar\u0131 bulmana yard\u0131mc\u0131 olur."
    )

    try:
        df = load_prepared_data()
    except Exception as exc:
        st.error(f"Veri y\u00fcklenirken hata olu\u015ftu: {exc}")
        st.stop()

    if df.empty:
        st.error("Hi\u00e7 veri y\u00fcklenemedi, \u00f6nce scraper'lar\u0131 \u00e7al\u0131\u015ft\u0131rman gerekiyor.")
        st.stop()

    with st.expander("Veri \u00f6zeti", expanded=False):
        st.write(f"Toplam kay\u0131t: {len(df)}")
        st.dataframe(df.head())

    preferences = build_preferences(df)
    if preferences is None:
        st.stop()

    filtered_df = df.copy()
    allowed_brands = preferences.get("allowed_brands")
    if allowed_brands:
        filtered_df = filtered_df[filtered_df["brand"].isin(allowed_brands)]

    allowed_oses = preferences.get("allowed_oses")
    if allowed_oses:
        filtered_df = filtered_df[filtered_df["os"].isin(allowed_oses)]

    min_ram = preferences.get("min_ram")
    if min_ram:
        filtered_df = filtered_df[filtered_df["ram_gb"] >= min_ram]

    min_ssd = preferences.get("min_ssd")
    if min_ssd:
        filtered_df = filtered_df[filtered_df["ssd_gb"] >= min_ssd]

    if preferences.get("usage_key") == "gaming" and preferences.get("exclude_apple_in_gaming"):
        filtered_df = filtered_df[filtered_df["brand"] != "apple"]

    if st.sidebar.button("\U0001F680 \u00d6nerileri Hesapla"):
        top_n = preferences.pop("top_n", 5)
        recs = scoring.get_recommendations(filtered_df, preferences, top_n=top_n)
        if recs.empty:
            st.warning("Filtreler \u00e7ok s\u0131k\u0131 olabilir, b\u00fct\u00e7eyi veya ama\u00e7lar\u0131 gev\u015fetmeyi dene.")
        else:
            show_recommendations_streamlit(recs, preferences)
    else:
        st.info("Soldan kriterlerini se\u00e7 ve **\U0001F680 \u00d6nerileri Hesapla** butonuna bas.")


if __name__ == "__main__":
    main()
