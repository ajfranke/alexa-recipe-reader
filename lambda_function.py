"""
Alexa Directions Template Application

(c) Arthur J. Franke, 2017

"""

from __future__ import print_function
import os
import time
import types
import re
import json

import boto3
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer


# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session,
    show_card = True, card_content = ""):

    response = {
        'outputSpeech': {
            'type': 'PlainText'
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText'
            }
        },
        'shouldEndSession': should_end_session
    }

    if show_card or card_content:
        response['card'] = {
            'type': 'Simple',
            'title': title
            }

        if card_content:
            response['card']['content'] = card_content
        else:
            response['card']['content'] = strip_ssml(output)

    # detect use of SSML in response
    if '<speak>' in output:
        response['outputSpeech']['type'] = 'SSML'
        response['outputSpeech']['ssml'] = output
    else:
        response['outputSpeech']['text'] = output
    # detect use of SSML in reprompt
    if reprompt_text and '<speak>' in reprompt_text:
        response['reprompt']['outputSpeech']['type'] = 'SSML'
        response['reprompt']['outputSpeech']['ssml'] = reprompt_text
    else:
        response['reprompt']['outputSpeech']['text'] = reprompt_text

    return response


def build_response(session_attributes, speechlet_response):
    return {
        'version': os.environ['VERSION'],
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- SSML Helper functions -------------------------------
def strip_ssml(ssml):
    ssmlre = re.compile('<[^>]+>')
    return re.sub(ssmlre, "", ssml)

def to_ssml(text):
    """Adds SSML headers to string.
    """
    return '<speak>'+ text + '</speak>'

def add_ssml_pause(duration):
    """Turns a duration into an SSML tag."""
    if duration:
        return '<break time="%s"/> ' % (duration)
    else:
        return ''

def step_to_ssml(step):
    return step['instruction']+add_ssml_pause(step['estimated_time'])

def done_this_step():
    return "Are you finished with this step?  "

# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """

    session_attributes = {}
    card_title = "Welcome to Recipe Reader!"
    speech_output = "Welcome to Recipe Reader.  Which set of instructions should I read?  " \
        "You can say begin song, or begin dance."

    reprompt_text = "Should I begin song, or begin dance?  "
    should_end_session = False

    return build_response(session_attributes, build_speechlet_response(
        card_title, to_ssml(speech_output), reprompt_text, should_end_session))


def get_help_response():
    """
    Describes functionality and options
    """
    session_attributes = {}
    card_title = "How to use Recipe Reader"
    speech_output = "Recipe Reader lets you navigate sets of instructions.  "\
        "To begin, say begin song to hear instructions for building a tune.  "\
        "Or you can say begin dance to hear instructions for a far-out dance.  "

    reprompt_text = "Try saying begin song to start."
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        card_title, to_ssml(speech_output), reprompt_text, should_end_session))


def handle_session_end_request():
    """Session end close-out and response"""
    card_title = "Signing Off"
    speech_output = ""
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response({}, build_speechlet_response(
        card_title, speech_output, None, should_end_session, show_card=False))


def start_instructions(intent, session):
    """Start a set of instructions based on slot value
    """
    sesh_attr = persist_attributes(session)

    chosen_set = str(get_slot_value(intent, "Recipe"))

    recipes = load_recipes()

    if chosen_set in recipes:
        recipe = recipes[chosen_set]
    else:
        return build_response({}, build_speechlet_response("Unknown Recipe",
            "I'm sorry, but I don't know that recipe.", None,
            should_end_session=True, show_card=False))

    # save recipe as part of session variables
    sesh_attr['recipe'] = recipe

    # begin preparing response
    title = recipe['title']
    speech = "Great!  Let's begin.  " + recipe['intro']

    # append begin message with first step of instructions
    first_step = recipe['recipe'][0]
    speech += "First, " + step_to_ssml(first_step)
    sesh_attr['last_step'] = first_step

    # log to database for cross-session use
    db_log_step(session['user']['userId'], recipe, first_step)

    return build_response(sesh_attr, build_speechlet_response(title,
        to_ssml(speech), reprompt_text=done_this_step(), should_end_session=False, show_card=False))


def load_recipes(filepath="recipes.json"):
    """
    Load recipe file
    """
    f = open(filepath, 'r')
    recipes = json.loads(f.read())
    f.close()

    return recipes


def get_yes_no(intent, session):
    """
    Handle a yes/no answer based on previous intent & follow-up question
    """
    sesh_attr = persist_attributes(session)

    if 'last_step' in sesh_attr and 'recipe' in sesh_attr:
        if intent['name'] == "AMAZON.YesIntent":
            return get_next(intent, session)
        else:
            return handle_session_end_request()

    return build_response(sesh_attr, build_speechlet_response("Not sure what you mean",
        "I am not sure which question you're answering.",
        reprompt_text=None, should_end_session=True, show_card=False))


def get_next(intent, session):
    """
    Move to  next item in instructions
    """
    sesh_attr = persist_attributes(session)
    userID = session['user']['userId']

    if 'last_step' in sesh_attr and 'recipe' in sesh_attr:
        recipe = sesh_attr['recipe']
        last_step = sesh_attr['last_step']
    else:
        full_last_step = db_get_last_step(userID)
        recipe = full_last_step['recipe']
        last_step = recipe['step']


    next_step = recipe_next_step(recipe, last_step)

    if next_step:
        # log to database for cross-session use
        db_log_step(userID, recipe, next_step)
        sesh_attr.update({'last_step': next_step, 'recipe': recipe})

        return build_response(sesh_attr, build_speechlet_response("Next Step",
            to_ssml(step_to_ssml(next_step)), reprompt_text=done_this_step(),
            should_end_session=False, show_card=False))
    else:
        return build_response(sesh_attr, build_speechlet_response(
            recipe['title']+": Finished!",
            to_ssml("That was the last step!  " + recipe['conclusion']),
            reprompt_text=None, should_end_session=True, show_card=False))


def recipe_next_step(recipe, step):
    """Compares a recipe and a step, and returns the next step
    """
    steps = recipe['recipe']
    try:
        return steps[steps.index(step)+1]
    except IndexError:
        return None


def set_pause(intent, session):
    """
    Pause instructions until resume is called for
    """
    sesh_attr = persist_attributes(session)

    return build_response(sesh_attr, build_speechlet_response("Waiting...",
        to_ssml(add_ssml_pause("10s")), reprompt_text=None,
        should_end_session=True, show_card=False))


def get_previous(intent, session):
    """
    Go back to previous step in instructions
    """
    sesh_attr = persist_attributes(session)
    userID = session['user']['userId']

    if 'last_step' in sesh_attr and 'recipe' in sesh_attr:
        recipe = sesh_attr['recipe']
        last_step = sesh_attr['last_step']
    else:
        full_last_step = db_get_last_step(userID)
        recipe = full_last_step['recipe']
        last_step = recipe['step']

    next_step = recipe_prior_step(recipe, last_step)

    # log to database for cross-session use
    db_log_step(userID, recipe, next_step)
    sesh_attr.update({'last_step': next_step, 'recipe': recipe})

    return build_response(sesh_attr, build_speechlet_response("Going Back",
            to_ssml(step_to_ssml(next_step)), reprompt_text=done_this_step(),
            should_end_session=False, show_card=False))


def recipe_prior_step(recipe, step):
    """Compares a recipe and a step, and returns the prior step
    """
    steps = recipe['recipe']
    if steps.index(step) == 0:
        return step

    return steps[steps.index(step)-1]


def get_repeat(intent, session):
    """
    Repeat the current step in instructions
    """
    sesh_attr = persist_attributes(session)
    userID = session['user']['userId']

    if 'last_step' in sesh_attr and 'recipe' in sesh_attr:
        last_step = sesh_attr['last_step']
    else:
        full_last_step = db_get_last_step(userID)
        last_step = recipe['step']

    return build_response(sesh_attr, build_speechlet_response("Replay Step",
            to_ssml(step_to_ssml(last_step)), reprompt_text=done_this_step(),
            should_end_session=False, show_card=False))


def get_start_over(intent, session):
    """
    Go back to the beginning of the instruction set
    """
    sesh_attr = persist_attributes(session)
    userID = session['user']['userId']

    if 'last_step' in sesh_attr and 'recipe' in sesh_attr:
        recipe = sesh_attr['recipe']
    else:
        ds = TypeDeserializer()
        full_last_step = db_get_last_step(userID)
        recipe = ds.deserialize(full_last_step['recipe'])

    next_step = recipe['recipe'][0]

    # log to database for cross-session use
    db_log_step(userID, recipe, next_step)
    sesh_attr.update({'last_step': next_step, 'recipe': recipe})

    return build_response(sesh_attr, build_speechlet_response("Starting Over",
            to_ssml(step_to_ssml(next_step)), reprompt_text=done_this_step(),
            should_end_session=False, show_card=False))


# --------------- Events ------------------------------------- #

def on_session_started(session_started_request, session):
    """ Called when the session starts

    Can be used to initialize values if used across intents.
    """

    print("on_session_started requestId=" + session_started_request['requestId']
          + ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without an intent
    """
    print("on_launch requestId=" + launch_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """
    Called when the user specifies an intent for this skill
    """
    print("on_intent requestId=" + intent_request['requestId'] +
          ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # Dispatch to your skill's intent handlers
    if intent_name == "StartIntent":
        return start_instructions(intent, session)
    elif intent_name in ['AMAZON.YesIntent','AMAZON.NoIntent']:
        return get_yes_no(intent, session)
    elif intent_name == "AMAZON.NextIntent":
        return get_next(intent, session)
    elif intent_name == "AMAZON.PauseIntent":
        return set_pause(intent, session)
    elif intent_name == "AMAZON.PreviousIntent":
        return get_previous(intent, session)
    elif intent_name == "AMAZON.RepeatIntent":
        return get_repeat(intent, session)
    elif intent_name == "AMAZON.ResumeIntent":
        return get_repeat(intent, session) # AJF: I think this might work?
    elif intent_name == "AMAZON.StartOverIntent":
        return get_start_over(intent, session)
    elif intent_name in ["AMAZON.HelpIntent"]:
        return get_help_response()
    elif intent_name in ["AMAZON.CancelIntent", "AMAZON.StopIntent"]:
        return handle_session_end_request()
    else:
        raise ValueError("Invalid intent")


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # add cleanup logic here


def persist_attributes(session):
    if 'attributes' in session.keys():
        return session['attributes']
    else:
        return {}


def get_slot_value(intent, slot_name, default=None, avoid=[""]):
    """Function to safely return a slot value from the dictionary.

    Only returns non-default value if intent contains a value for the slot,
    and that value is not an empty string.
    """
    if slot_name in intent['slots'] and "value" in intent['slots'][slot_name] \
        and intent['slots'][slot_name]['value'] not in avoid:
        # only return
        return intent['slots'][slot_name]['value']
    else:
        return default

# --------------- Main handler ------------------

def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print("event.session.application.applicationId=" +
          event['session']['application']['applicationId'])

    #Application ID to prevent someone else from calling this function.
    if (event['session']['application']['applicationId'] !=
            os.environ['SKILL_ID']):
        raise ValueError("Invalid Application ID")

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    if event['request']['type'] == "LaunchRequest":
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])


# ---------------------- Speech helper functions ----------------------

def comma_conjoin(inlist, conjunction):
    """Parses the elements of a list into a string joined by commas,
    with an 'and' before the final element.  Oxford comma!
    """
    if len(inlist) == 0:
        return ""
    elif len(inlist) == 1:
        return str(inlist.pop())
    elif len(inlist) == 2:
        return (" " + conjunction + " ").join(inlist)

    text = ", " + conjunction + " " + inlist.pop()
    text = ", ".join(inlist) + text

    return text

def comma_and(inlist):
    """Parses the elements of a list into a string joined by commas,
    with an 'and' before the final element.
    """
    return comma_conjoin(inlist, "and")

def comma_or(inlist):
    """Parses the elements of a list into a string joined by commas,
    with an 'or' before the final element.
    """
    return comma_conjoin(inlist, "or")

# --------------- DynamoDB Helper calls ------------------------------ #


def db_connect():
    return boto3.client('dynamodb', aws_access_key_id=os.environ['AWS_KEY_ID'],
                            aws_secret_access_key=os.environ['AWS_SECRET'])


def db_log_step(userID, recipe, step):
    """Log the most recent step that a user has been given
    """
    dynamo = db_connect()
    ts = TypeSerializer()

    put_resp = dynamo.put_item(TableName=os.environ['STEP_HISTORY_TABLE'],
                    Item={'userID': {'S': userID},
                        'time': {'N': str(time.time())},
                        'step': ts.serialize(step),
                        'recipe': ts.serialize(recipe)
                    })

    upd_resp = dynamo.update_item(TableName=os.environ['STEP_LAST_TABLE'],
                    Key={'userID': {'S': userID}},
                    AttributeUpdates={'step': {'Action': 'PUT', 'Value': ts.serialize(step)},
                        'recipe': {'Action': 'PUT', 'Value': ts.serialize(recipe)}}
                    )

    return (put_resp, upd_resp)

def db_get_last_step(userID):
    """Get the most recent step that a user has executed
    """
    dynamo = db_connect()
    ds = TypeDeserializer()

    response = dynamo.get_item(TableName=os.environ['STEP_LAST_TABLE'],
                    Key={'userID': {'S': userID}})

    return response['Item']
