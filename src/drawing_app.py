import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
import requests
import json
import os
from dotenv import load_dotenv
from pathlib import Path

# ページの設定（余白を最小限に）
st.set_page_config(
    layout="wide",
    initial_sidebar_state="collapsed"
)

# カスタムCSS
st.markdown("""
    <style>
        .block-container {
            padding: 0rem;
        }
        .stButton button {
            width: 100%;
            height: 50px;
        }
        section[data-testid="stSidebar"] {
            width: 200px !important;
        }
        /* フッターを非表示 */
        footer {
            display: none;
        }
        /* ヘッダーを非表示 */
        header {
            display: none;
        }
    </style>
""", unsafe_allow_html=True)

# .envファイルの読み込み
dotenv_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path)

SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL')

if not SLACK_TOKEN or not SLACK_CHANNEL:
    st.error("Slack設定が見つかりません。.envファイルを確認してください。")
    st.stop()

def send_to_slack(img_byte_arr):
    try:
        file_size = len(img_byte_arr)
        headers = {
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        upload_url_response = requests.get(
            "https://slack.com/api/files.getUploadURLExternal",
            headers=headers,
            params={"filename": "memo.png", "length": str(file_size)}
        )

        if not upload_url_response.ok:
            raise Exception("Failed to get upload URL")

        upload_data = upload_url_response.json()
        if not upload_data.get('ok'):
            raise Exception(f"Slack API Error: {upload_data.get('error')}")

        upload_response = requests.post(
            upload_data['upload_url'],
            files={'file': ('memo.png', img_byte_arr, 'image/png')}
        )

        if not upload_response.ok:
            raise Exception("Failed to upload file")

        complete_payload = {
            "files": [{"id": upload_data['file_id']}],
            "channel_id": SLACK_CHANNEL
        }
        complete_response = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers={
                "Authorization": f"Bearer {SLACK_TOKEN}",
                "Content-Type": "application/json"
            },
            data=json.dumps(complete_payload)
        )

        if not complete_response.ok:
            raise Exception("Failed to complete upload")

        return True

    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
        return False

def main():
    # サイドバーの設定
    with st.sidebar:
        stroke_width = st.slider("線の太さ", 1, 25, 3)
        stroke_color = st.color_picker("線の色", "#000000")
        bg_color = st.color_picker("背景色", "#ffffff")

    # 画面サイズの取得
    # デフォルトの余白を考慮して調整
    canvas_width = 2000
    canvas_height = 800

    # キャンバス
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        background_color=bg_color,
        height=canvas_height,
        width=canvas_width,
        drawing_mode="freedraw",
        key="canvas",
    )

    # ボタンを横並びに配置
    col1, col2 = st.columns(2)
    with col1:
        if st.button("クリア", key="clear"):
            st.session_state.canvas_key = st.session_state.get('canvas_key', 0) + 1
            st.experimental_rerun()

    with col2:
        if st.button("Slackに送信", key="send"):
            if canvas_result.image_data is not None:
                img = Image.fromarray(canvas_result.image_data.astype('uint8'))
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()

                with st.spinner('送信中...'):
                    if send_to_slack(img_byte_arr):
                        st.success("送信完了")
            else:
                st.warning("描画データがありません")

if __name__ == "__main__":
    main()
