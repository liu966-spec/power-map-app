import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import os

# 設定網頁標題
st.set_page_config(page_title="電力供應範圍查詢", layout="wide")

def create_popup_html(row):
    # 設定固定寬度 (例如 250px)，並強制長文字換行
    html = f"""
    <div style="
        font-family: 'Microsoft JhengHei', sans-serif; 
        width: 250px; 
        white-space: normal; 
        word-wrap: break-word;
        line-height: 1.5;
    ">
        <b style="font-size: 16px; color: #E74C3C;">⚡ {row['名稱']}</b><br>
        <hr style="margin: 5px 0;">
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <tr><td style="width: 60px; vertical-align: top;"><b>類別：</b></td><td>{row.get('類別', 'N/A')}</td></tr>
            <tr><td style="width: 60px; vertical-align: top;"><b>變壓器：</b></td><td>{row.get('變壓器別', 'N/A')}</td></tr>
            <tr><td style="width: 60px; vertical-align: top;"><b>地址：</b></td><td>{row['地址']}</td></tr>
        </table>
    </div>
    """
    # max_width 設為比 div 寬一點點，確保滾動條不出現
    return folium.Popup(html, max_width=300)

# --- 1. 讀取本地 GeoJSON 檔案 ---
@st.cache_data
def load_local_geojson(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        st.error(f"找不到檔案：{file_path}，請確認檔案路徑是否正確。")
        return None

# 假設您的檔名是 '鄉鎮市區界線(TWD97經緯度).json'，請根據實際檔名修改
GEO_FILE = "鄉鎮市區界線(TWD97經緯度).json" 
geojson_data = load_local_geojson(GEO_FILE)

st.title("⚡ 變電站區域供電範圍查詢系統")

# --- 2. 上傳變電站 Excel ---
uploaded_file = st.file_uploader("請上傳變電站 Excel 檔案", type=["xlsx"])

if uploaded_file and geojson_data:
    df = pd.read_excel(uploaded_file)
    
    # 側邊欄：選擇變電站
    st.sidebar.header("篩選控制台")
    selected_name = st.sidebar.selectbox("請選擇變電站名稱：", df['名稱'].unique())
    
    # 取得該變電站資料
    row = df[df['名稱'] == selected_name].iloc[0]
    target_area = str(row['供電範圍']).strip() # 例如: "板橋區"

    # --- 3. 建立地圖 ---
    # 使用座標點作為中心，若無座標則預設台灣中心
    map_center = [row['緯度'], row['經度']] if not pd.isna(row['緯度']) else [23.5, 121.0]
    m = folium.Map(location=map_center, zoom_start=12, tiles=None)

    # 加入國土測繪中心底圖
    folium.TileLayer(
        tiles="https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}",
        attr="© 內政部國土測繪中心",
        name="國土測繪中心-電子地圖",
        overlay=False
    ).add_to(m)

# --- 4. 針對您的 JSON 格式優化的跨縣市/複合層級篩選邏輯 ---
    import re
    raw_range = str(row['供電範圍']).strip()
    # 拆分 Excel 供電範圍內容 (支援：基隆市、新北市汐止區、宜蘭縣 等)
    target_areas = [a.strip() for a in re.split(r'[、,， \s]', raw_range) if a.strip()]
    
    filtered_features = []
    
    # 根據您的 JSON 內容，屬性名稱通常為：
    found_county_key = 'COUNTYNAME' # 縣市名
    found_town_key = 'TOWNNAME'     # 鄉鎮名

    for f in geojson_data['features']:
        props = f['properties']
        this_county = str(props.get(found_county_key, "")) # 範例: "宜蘭縣"
        this_town = str(props.get(found_town_key, ""))     # 範例: "北投區"
        # 組合名稱，用於匹配「新北市汐止區」這種寫法
        combined_name = this_county + this_town 
        
        for area in target_areas:
            # 匹配條件：
            # 1. Excel 寫縣市名 (如 "宜蘭縣") -> 抓取該縣市所有鄉鎮
            # 2. Excel 寫鄉鎮名 (如 "北投區") -> 精確抓取該區
            # 3. Excel 寫複合名 (如 "新北市汐止區") -> 匹配 combined_name
            if area == this_county or area == this_town or area == combined_name:
                filtered_features.append(f)
                break 

    if filtered_features:
        # 移除重複選取的 Feature
        unique_features = []
        seen_ids = set()
        for feat in filtered_features:
            # 建立唯一的 ID (縣市 + 鄉鎮)
            fid = f"{feat['properties'].get(found_county_key, '')}{feat['properties'].get(found_town_key, '')}"
            if fid not in seen_ids:
                unique_features.append(feat)
                seen_ids.add(fid)

        filtered_geojson = {"type": "FeatureCollection", "features": unique_features}
        
        # 繪製範圍
        folium.GeoJson(
            filtered_geojson,
            style_function=lambda x: {
                'fillColor': 'orange',
                'color': 'darkred',
                'weight': 2,
                'fillOpacity': 0.4
            },
            tooltip=folium.GeoJsonTooltip(
                fields=[found_county_key, found_town_key],
                aliases=['縣市:', '鄉鎮:']
            )
        ).add_to(m)
        
        st.success(f"✅ 已成功標記供電範圍：{', '.join(target_areas)}")
    else:
        st.warning(f"❌ 找不到與「{raw_range}」匹配的邊界。")

    # --- 5. 標記變電站點 ---
    popup_obj = create_popup_html(row)
    
    folium.Marker(
        [row['緯度'], row['經度']],
        popup=popup_obj,
        tooltip=row['名稱'],
        icon=folium.Icon(color='red', icon='bolt', prefix='fa')
    ).add_to(m)

    # 顯示地圖
    st_folium(m, width="100%", height=650)

elif not uploaded_file:
    st.info("請上傳 Excel 檔案以開始。")