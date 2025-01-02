from kivymd.app import MDApp
from kivy.uix.widget import Widget
from kivy.graphics import Line
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.spinner import MDSpinner
from kivy.clock import Clock, mainthread
import requests
import json
import os
import threading
from dotenv import load_dotenv
from pathlib import Path


dotenv_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path)


class DrawingWidget(Widget):
    def on_touch_down(self, touch):
        with self.canvas:
            touch.ud['line'] = Line(points=(touch.x, touch.y), width=2)

    def on_touch_move(self, touch):
        touch.ud['line'].points += [touch.x, touch.y]

class DrawingApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.slack_token = os.getenv('SLACK_TOKEN')
        self.slack_channel = os.getenv('SLACK_CHANNEL')
        if not self.slack_token or not self.slack_channel:
            raise ValueError("Slack設定が見つかりません。.envファイルを確認してください。")
    def build(self):
        self.layout = BoxLayout(orientation='vertical')
        button_layout = BoxLayout(orientation='horizontal', size_hint=(1, 0.1))
        self.theme_cls.theme_style = "Dark"

        self.drawing = DrawingWidget()
        self.layout.add_widget(self.drawing)

        self.send_button = Button(text='Send To Slack')
        self.send_button.bind(on_press=self.start_sending)

        clear_button = Button(text='Clear')
        clear_button.bind(on_press=self.clear_canvas)

        self.spinner = MDSpinner(
            size_hint=(None, None),
            size=(46, 46),
            pos_hint={'center_x': .5, 'center_y': .5},
            active=False
        )

        button_layout.add_widget(clear_button)
        button_layout.add_widget(self.send_button)
        self.layout.add_widget(button_layout)

        return self.layout

    def clear_canvas(self, instance):
        self.drawing.canvas.clear()

    def start_sending(self, instance):
        self.send_button.disabled = True
        self.send_button.text = 'Sending...'
        self.layout.add_widget(self.spinner)
        self.spinner.active = True

        # メインスレッドで画像をエクスポート
        self.drawing.export_to_png('temp_memo.png')
        # 別スレッドでSlackへの送信を実行
        threading.Thread(target=self.send_to_slack_thread).start()

    def send_to_slack_thread(self):
        try:
            token = self.slack_token
            channel = self.slack_channel

            file_size = os.path.getsize('temp_memo.png')

            # Step 1: アップロードURL取得
            headers = {
                "Authorization": f"Bearer {token}",
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

            # Step 2: ファイルアップロード
            with open('temp_memo.png', 'rb') as f:
                upload_response = requests.post(
                    upload_data['upload_url'],
                    files={'file': f}
                )

            if not upload_response.ok:
                raise Exception("Failed to upload file")

            # Step 3: アップロード完了
            complete_payload = {
                "files": [{"id": upload_data['file_id']}],
                "channel_id": channel
            }
            complete_response = requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(complete_payload)
            )

            if not complete_response.ok:
                raise Exception("Failed to complete upload")

            # 成功時の処理
            Clock.schedule_once(self.finish_sending)

        except Exception as e:
            print(f"Error: {str(e)}")
            Clock.schedule_once(lambda dt: self.handle_error())
        finally:
            # 一時ファイルの削除
            if os.path.exists('temp_memo.png'):
                os.remove('temp_memo.png')

    @mainthread
    def finish_sending(self, dt=None):
        self.spinner.active = False
        self.layout.remove_widget(self.spinner)
        self.send_button.disabled = False
        self.send_button.text = 'Send To Slack'

    @mainthread
    def handle_error(self, dt=None):
        self.spinner.active = False
        self.layout.remove_widget(self.spinner)
        self.send_button.disabled = False
        self.send_button.text = 'Error Occurred'

if __name__ == '__main__':
    DrawingApp().run()
