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
            }
            .control-panel {
                padding: 10px;
                background-color: #f8f9fa;
                border-bottom: 1px solid #ddd;
                display: flex;
                align-items: center;
            }
            .button {
                margin: 5px;
                padding: 10px 20px;
                font-size: 16px;
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
                align-items: center;
            }
            .input-label {
                margin-right: 5px;
                font-size: 14px;
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
        html.Div([
            html.Label('線の太さ:', className='input-label'),
            dcc.Input(
                id='stroke-width',
                type='number',
                value=3,
                min=1,
                max=25,
                className='color-picker'
            ),
        ], className='input-group'),
        html.Div([
            html.Label('線の色:', className='input-label'),
            dcc.Input(
                id='stroke-color',
                type='text',
                value='#000000',
                pattern='^#[A-Fa-f0-9]{6}$',
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
                'width': 2000,
                'height': 800,
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
        config={
            'modeBarButtonsToAdd': [
                'drawline',
                'drawopenpath',
                'drawclosedpath',
                'drawcircle',
                'drawrect',
                'eraseshape'
            ],
            'modeBarButtonsToRemove': [
                'zoom',
                'pan',
                'select',
                'zoomIn',
                'zoomOut',
                'autoScale',
                'resetScale'
            ],
            'displaylogo': False,
            'responsive': True
        }
    ),

    # 描画データの保存用
    dcc.Store(id='drawing-data', data=[]),

    # メッセージ表示エリア
    html.Div(id='message-area')
])

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
    [Output('canvas', 'figure'),
     Output('drawing-data', 'data')],
    [Input('canvas', 'relayoutData'),
     Input('clear-button', 'n_clicks'),
     Input('stroke-width', 'value'),
     Input('stroke-color', 'value')],
    [State('drawing-data', 'data'),
     State('canvas', 'figure')],
    prevent_initial_call=True
)
def update_figure(relayout_data, clear_clicks, stroke_width, stroke_color, drawing_data, current_figure):
    ctx = callback_context
    if not ctx.triggered:
        return current_figure, drawing_data

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'clear-button':
        figure = {
            'data': [],
            'layout': {
                'width': 2000,
                'height': 800,
                'paper_bgcolor': 'white',
                'plot_bgcolor': 'white',
                'dragmode': 'drawopenpath',
                'newshape': {
                    'line': {
                        'color': stroke_color,
                        'width': stroke_width,
                    },
                    'fillcolor': stroke_color,
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
        return figure, []

    if triggered_id == 'canvas' and relayout_data:
        if 'shapes' in relayout_data:
            drawing_data = relayout_data['shapes']
        elif any(key.startswith('shapes[') for key in relayout_data.keys()):
            # 形状の更新
            current_shapes = current_figure['layout'].get('shapes', [])
            for key, value in relayout_data.items():
                if key.startswith('shapes['):
                    idx = int(key.split('[')[1].split(']')[0])
                    prop = key.split('.')[-1]
                    if idx >= len(current_shapes):
                        current_shapes.append({})
                    current_shapes[idx][prop] = value
            drawing_data = current_shapes

    current_figure['layout']['shapes'] = drawing_data
    current_figure['layout']['newshape']['line']['color'] = stroke_color
    current_figure['layout']['newshape']['line']['width'] = stroke_width
    current_figure['layout']['newshape']['fillcolor'] = stroke_color

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
    app.run_server(debug=True, host='0.0.0.0', port=8050)
