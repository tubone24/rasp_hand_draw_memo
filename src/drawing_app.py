from dash import Dash, html, dcc, Input, Output, State, callback_context
import plotly.graph_objects as go
import json
import os
from dotenv import load_dotenv
from pathlib import Path
import numpy as np
import requests
from PIL import Image
import io
import base64
import plotly.io

# 環境変数の読み込み
dotenv_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path)

SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL')

# Dashアプリケーションの初期化
app = Dash(__name__)

# カスタムCSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                margin: 0;
                padding: 0;
                font-size: 6px;
                overflow: hidden;
            }
            .control-panel {
                padding: 5px;
                background-color: #f8f9fa;
                border-bottom: 1px solid #ddd;
                display: flex;
                height: 30px;
                align-items: center;
            }
            .button {
                margin: 2px;
                padding: 5px 10px;
                font-size: 6px;
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            .button:hover {
                background-color: #0056b3;
            }
            .input-group {
                margin: 0 10px;
                display: flex;
                width: 10px;
                align-items: center;
            }
            .input-label {
                margin-right: 5px;
                font-size: 6px;
            }
            .color-picker {
                margin: 5px;
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# レイアウトの定義
app.layout = html.Div([
    # コントロールパネル
    html.Div([
        html.Button('クリア', id='clear-button', className='button'),
        html.Button('Slackに送信', id='send-button', className='button'),
        html.Button('全画面表示', id='fullscreen-button',n_clicks=0, className='button'),
        html.Div([
            html.Label('線の太さ:', className='input-label'),
            dcc.Input(
                id='stroke-width',
                type='number',
                value=5,
                min=1,
                max=25,
                className='color-picker'
            ),
        ], className='input-group'),
    ], className='control-panel'),

    # 描画キャンバス
    dcc.Graph(
        id='canvas',
        figure={
            'data': [],
            'layout': {
                'width': None,
                'height': None,
                'autosize': True,
                'paper_bgcolor': 'white',
                'plot_bgcolor': 'white',
                'dragmode': 'drawopenpath',
                'newshape': {
                    'line': {
                        'color': '#000000',
                        'width': 3,
                    },
                    'fillcolor': '#000000',
                    'opacity': 0.3
                },
                'xaxis': {
                    'showgrid': False,
                    'showticklabels': False,
                    'zeroline': False,
                    'range': [0, 2000]
                },
                'yaxis': {
                    'showgrid': False,
                    'showticklabels': False,
                    'zeroline': False,
                    'range': [0, 800],
                    'scaleanchor': 'x'
                },
                'margin': {'l': 0, 'r': 0, 't': 0, 'b': 0},
                'shapes': []
            }
        },
        style={'height': 'calc(100vh - 60px)'},
        config={
            'modeBarButtonsToAdd': [
                'drawopenpath',
                'fullscreen',
            ],
            'modeBarButtonsToRemove': [
                'zoom',
                'pan',
                'select',
                'zoomIn',
                'zoomOut',
                'autoScale',
                'resetScale',
                'drawline',
                'drawclosedpath',
                'drawcircle',
                'drawrect',
                'eraseshape'
            ],
            'displaylogo': False,
            'responsive': True,
            'scrollZoom': False,
        }
    ),

    # 描画データの保存用
    dcc.Store(id='drawing-data', data=[]),

    # メッセージ表示エリア
    html.Div(id='message-area')
])

app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks > 0) {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
            } else {
                if (document.exitFullscreen) {
                    document.exitFullscreen();
                }
            }
        }
        return '';
    }
    """,
    Output('fullscreen-button', 'n_clicks'),
    Input('fullscreen-button', 'n_clicks'),
)

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
        print(f"エラーが発生しました: {str(e)}")
        return False

@app.callback(
    Output('canvas', 'figure'),
    Input('clear-button', 'n_clicks'),
    prevent_initial_call=True
)
def clear_canvas(n_clicks):
    if n_clicks is None:
        raise PreventUpdate

    # 初期状態のfigureを返す
    return {
        'data': [],
        'layout': {
            'width': None,
            'height': None,
            'autosize': True,
            'paper_bgcolor': 'white',
            'plot_bgcolor': 'white',
            'dragmode': 'drawopenpath',
            'newshape': {
                'line': {
                    'color': '#000000',
                    'width': 3,
                },
                'fillcolor': '#000000',
                'opacity': 0.3
            },
            'xaxis': {
                'showgrid': False,
                'showticklabels': False,
                'zeroline': False,
                'range': [0, 2000]
            },
            'yaxis': {
                'showgrid': False,
                'showticklabels': False,
                'zeroline': False,
                'range': [0, 800],
                'scaleanchor': 'x'
            },
            'margin': {'l': 0, 'r': 0, 't': 0, 'b': 0},
            'shapes': []
        }
    }

@app.callback(
    [Output('canvas', 'figure', allow_duplicate=True),
     Output('drawing-data', 'data')],
    [Input('canvas', 'relayoutData'),
     Input('stroke-width', 'value')],
    [State('drawing-data', 'data'),
     State('canvas', 'figure')],
    prevent_initial_call=True
)
def update_figure(relayout_data, stroke_width, drawing_data, current_figure):
    ctx = callback_context
    if not ctx.triggered:
        return current_figure, drawing_data

    if relayout_data:
        current_figure['layout']['dragmode'] = 'drawopenpath'

    return current_figure, drawing_data
@app.callback(
    [Output('message-area', 'children'),
     Output('send-button', 'disabled')],
    Input('send-button', 'n_clicks'),
    State('canvas', 'figure'),
    prevent_initial_call=True
)
def send_to_slack_callback(n_clicks, figure):
    if n_clicks is None:
        return ''

    img_bytes = plotly.io.to_image(figure, format='png')

    if send_to_slack(img_bytes):
        return html.Div('送信完了', style={'color': 'green'}), False
    else:
        return html.Div('送信失敗', style={'color': 'red'}), False


if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8050)