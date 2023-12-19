import asyncio
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from gpt_researcher.master.agent import GPTResearcher
from backend.utils import write_md_to_pdf
from gpt_researcher.utils.google_pub import PublishManager
import jwt
import datetime
import os
import json

# Set the Google Cloud project and Pub/Sub topic
project_id = "clean-silo-630"
sub_topic_name = "internal-researcher-local"
pub_topic_name = "internal-gateway-local2"
auth_file = 'gpt_researcher/config/AUTH.json'
publish_manager = PublishManager()

class SubscribeManager:
    """Manage Google PubSub"""
    def __init__(self):
        """Initialize the Google PubSub class."""
        credentials = service_account.Credentials.from_service_account_file(auth_file)
        self.subscriber = pubsub_v1.SubscriberClient(credentials=credentials)

    def callback(self, message):
        print(f"Received message ID: {message.message_id}.")
        data = message.data.decode('utf-8')
        secret_key = os.environ["INTERNAL_SECERT_KEY"]
        json_data = json.loads(data)
        payload = json_data.get("message")
        message_type = json_data.get("message_type")
        try:
            decoded_payload = jwt.decode(payload, secret_key, algorithms='HS256')
            task = decoded_payload.get("task")
            report_type = decoded_payload.get("report_type")
            user_id = decoded_payload.get("user_id")
            if task and report_type:
                asyncio.run(self.handle_researcher(message, task, report_type, message_type, user_id))
                message.ack()
            else:
                print("Error: not enough parameters provided.")
                message.ack()
        except Exception as e:
            print(f"Error SUB: {e}")
            publish_manager.publish_message({"type": "error", "output": f"ERROR : {e}", "message_type": message_type, "user_id": user_id})
            message.ack()

    async def start_subscriber(self):
        """Start the subscriber task."""
        # credentials = service_account.Credentials.from_service_account_file(auth_file)
        subscription_path = self.subscriber.subscription_path(project_id, sub_topic_name)
        subscriber = self.subscriber
        flow_control = pubsub_v1.types.FlowControl(max_messages=5)
        subscriber.subscribe(subscription_path, callback=self.callback, flow_control=flow_control)
        print(f"Listening for messages on {sub_topic_name}...")

    async def run_agent(self, task, report_type, websocket, message_type, user_id):
        """Run the agent."""
        # measure time
        start_time = datetime.datetime.now()
        # add customized JSON config file path here
        config_path = None
        # run agent
        researcher = GPTResearcher(task, report_type, config_path, websocket, message_type, user_id)
        report = await researcher.run(message_type, user_id)
        # measure time
        end_time = datetime.datetime.now()
        publish_manager.publish_message({"type": "logs", "output": f"\nTotal run time: {end_time - start_time}\n", "message_type": message_type, "user_id": user_id})
        return report

    async def handle_researcher(self, message, task, report_type, message_type, user_id):
        report = await self.run_agent(task, report_type, None, message_type, user_id)
        path = await write_md_to_pdf(report)
        publish_manager.publish_message({"type": "path", "output": path, "message_type": message_type, "user_id": user_id})
        message.ack()
        return 'true'