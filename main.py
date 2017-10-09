# -*- coding: utf-8 -*-
import os
import sys
import urllib
import requests
import json
from flask import Flask, request, Response, make_response
from contextlib import closing
# Twilio Helper Library
from twilio.twiml.voice_response import VoiceResponse, Gather
# AWS Python SDK
import boto3

# Setup global variables
apiai_client_access_key = os.environ["APIAPI_CLIENT_ACCESS_KEY"]

apiai_url = "https://api.api.ai/v1/query"
apiai_querystring = {"v": "20150910"}
registered_users = {"+447477471234": "Ameer",
                   "+447481191234": "Doug"
}
# Adjust the hints for improved Speech to Text
hints = "1 one first, 2 two second, 20 twenty, 25 twentyfifth, 6 sixth twentysixth, sir albert, westin, hyatt, inter continental, march, april, may, june"

app = Flask(__name__)

@app.route('/start', methods=['GET','POST'])
def start():
    caller_phone_number = request.values.get('From')
    user_id = request.values.get('CallSid')
    twilio_asr_language = request.values.get('twilio_asr_language', "en-US")
    apiai_language = request.values.get('apiai_language', "en")
    caller_name = registered_users.get(caller_phone_number, " ")
    hostname = request.url_root

    # Initialize API.AI Bot
    headers = {
        'authorization': "Bearer " + apiai_client_access_key,
        'content-type': "application/json"
    }
    payload = {'event': {'name':'book_hotel_welcome', 'data': {'user_name': caller_name}},
               'lang': apiai_language,
               'sessionId': user_id
    }
    response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    print(response.text)
    output = json.loads(response.text)
    output_text = output['result']['fulfillment']['speech']
    output_text = output_text.decode("utf-8")
    resp = VoiceResponse()
    # Prepare for next set of user Speech
    values = {"prior_text": output_text}
    qs = urllib.urlencode(values)
    action_url = "/process_speech?" + qs
    gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")
    # TTS the bot response

    qs = urllib.urlencode(values)
    gather.say(output_text, voice='brian', language='en')
    resp.append(gather)

    # If gather is missing (no speech), redirect to process speech again
    values = {"prior_text": output_text,
              "twilio_asr_language": twilio_asr_language,
              "apiai_language": apiai_language,
              "SpeechResult": "",
              "Confidence": 0.0
    }
    qs = urllib.urlencode(values)
    action_url = "/process_speech?" + qs
    resp.redirect(action_url)
    print str(resp)
    return str(resp)

#####
##### Process Twilio ASR: Text to Intent analysis
#####
@app.route('/process_speech', methods=['GET', 'POST'])
def process_speech():
    user_id = request.values.get('CallSid')
    twilio_asr_language = request.values.get('twilio_asr_language', "en-US")
    apiai_language = request.values.get('apiai_language', "en")
    prior_text = request.values.get('prior_text', "Prior text missing")
    prior_dialog_state = request.values.get('prior_dialog_state', "ElicitIntent")
    input_text = request.values.get("SpeechResult", "")
    confidence = float(request.values.get("Confidence", 0.0))
    hostname = request.url_root
    print "Twilio Speech to Text: " + input_text + " Confidence: " + str(confidence)
    sys.stdout.flush()

    resp = VoiceResponse()
    if (confidence > 0.5):
        # Step 1: Call Bot for intent analysis - API.AI Bot
        intent_name, output_text, dialog_state = apiai_text_to_intent(apiai_client_access_key, input_text, user_id, apiai_language)

        # Step 2: Construct TwiML
        if dialog_state in ['in-progress']:
            values = {"prior_text": output_text, "prior_dialog_state": dialog_state}
            qs2 = urllib.urlencode(values)
            action_url = "/process_speech?" + qs2
            gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url,method="POST")
            values = {"text": output_text,
                    "region": "us-east-1"
            }
            gather.say(output_text, voice='brian', language='en')
            resp.append(gather)

            # If gather is missing (no speech), redirect to process incomplete speech via the Bot
            values = {"prior_text": output_text,
                      "twilio_asr_language": twilio_asr_language,
                      "apiai_language": apiai_language,
                      "SpeechResult": "",
                      "Confidence": 0.0}
            qs3 = urllib.urlencode(values)
            action_url = "/process_speech?" + qs3
            resp.redirect(action_url)
        elif dialog_state in ['complete']:
            values = {"text": output_text,
                    "region": "us-east-1"
            }
            qs = urllib.urlencode(values)
            resp.say(output_text, voice='brian', language='en')
            resp.hangup()
        elif dialog_state in ['Failed']:
            values = {"text": "I am sorry, there was an error.  Please call again!",
                    "region": "us-east-1"
            }
            qs = urllib.urlencode(values)
            gather.say(output_text, voice='brian', language='en')
            resp.hangup()
    else:
        # We didn't get STT of higher confidence, replay the prior conversation
        output_text = prior_text
        dialog_state = prior_dialog_state
        values = {"prior_text": output_text,
                  "twilio_asr_language": twilio_asr_language,
                  "apiai_language": apiai_language,
                  "prior_dialog_state": dialog_state}
        qs2 = urllib.urlencode(values)
        action_url = "/process_speech?" + qs2
        gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")
        values = {"text": output_text,
                  "region": "us-east-1"
                  }
        qs1 = urllib.urlencode(values)
        gather.say(output_text, voice='brian', language='en')
        resp.append(gather)

        values = {"prior_text": output_text,
                  "twilio_asr_language": twilio_asr_language,
                  "apiai_language": apiai_language,
                  "prior_dialog_state": dialog_state
                  }
        qs2 = urllib.urlencode(values)
        action_url = "/process_speech?" + qs2
        resp.redirect(action_url)
    print str(resp)
    return str(resp)

#####
##### Google Api.ai - Text to Intent
#####
#@app.route('/apiai_text_to_intent', methods=['GET', 'POST'])
def apiai_text_to_intent(apiapi_client_access_key, input_text, user_id, language):
    headers = {
        'authorization': "Bearer " + apiapi_client_access_key,
        'content-type': "application/json"
    }
    payload = {'query': input_text,
               'lang': language,
               'sessionId': user_id
    }
    response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    output = json.loads(response.text)
    print json.dumps(output, indent=2)
    try:
        output_text = output['result']['fulfillment']['speech']
    except:
        output_text = ""
    try:
        intent_stage = output['result']['contexts']
    except:
        intent_stage = "unknown"

    if (output['result']['actionIncomplete']):
        dialog_state = 'in-progress'
    else:
        dialog_state = 'complete'

    return intent_stage, output_text, dialog_state

#####
##### API.API fulfillment webhook (You can enable this in API.AI console)
#####
@app.route('/apiai_fulfillment', methods=['GET', 'POST'])
def apiai_fulfillment():
    res = {"speech": "Your booking is confirmed. Have a great day!",
        "displayText": "Your booking is confirmed. Have a great day!",
        "source": "apiai-bookhotel-webhook"
    }
    res = json.dumps(res)
    r = make_response(res)
    r.headers['Content-Type'] = 'application/json'
    print str(r)
    return r

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug = True)
