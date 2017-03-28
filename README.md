# Recipe Reader Alexa skill

Utilizes Amazon built-in audio directive intents (play, next, repeat, etc.) to let the user navigate a list of instructions.  Example skill written in Python, based off of Amazon's Custom Skill example.  Utilizes Amazon DynamoDB to 'give Alexa a memory' across sessions.   

## Setup

1.  Clone the repository
2.  Create the skill interaction model using `intent_schema.json` and `utterances.txt`.
* Use `en-US` language.
* Create a custom slot type called `RECIPE_LIST` with slot values `dance` and `song`.
3.  Create a Python language Amazon Lambda using `lambda_function.py`.  
* Be sure to also upload `recipes.json` and `silent_48k.mp3`.  The included `prep.zip` file makes uploading these files as a single zip archive very easy.
* Set the following environmental variables:
| Variable Name | Value Description |
| :--- | :--- |
| `SKILL_ID` | Synchronize with your Alexa Skilly ID |
| `VERSION` | Version number of your function.  Kind of optional. |
| `STEP_HISTORY_TABLE` | Name of a DynamoDB table indexed on `{S: userID }` and secondary sort index `{N: time }` |
| `STEP_LAST_TABLE` | Name of a DynamoDB indexed on `{S: userID }`
| `AWS_KEY_ID` | Amazon AWS Key ID that provides access to DynamoDB. |
| `AWS_SECRET` | Amazon AWS secret that matches `AWS_KEY_ID`. |

4. Configure skill with Python Lambda ARN.  Account linking is not needed.
5. Test and enjoy!

## Recipe Store `recipes.json`

This file contains the recipes utilized by the skill, in JSON.  Recipe object names should match the slot values of `RECIPE_LIST` as configured above.  Recipe objects have the following layout:

```json
{
  "recipe name":{
    "title": "[will be shown in skill cards]",
    "intro": "[read at the beginning of the recipe]",
    "conclusion": "[read at the end of the recipe]",
    "prerequisites": ["items", "read off at", "the beginning"],
    "recipe": [
      {"instruction": "[text read to the user describing the first step]", "estimated_time": "5s"},
      {"instruction": "[text read to the user describing the second step]", "estimated_time": "5s"},
      {"instruction": "[etc. etc. sequentially]", "estimated_time": "5s"}
    ]
  }
}
```
The `instruction` objects within the `recipe` list are sequential.  The `estimated_time` string within each instruction object determines how long Alexa pauses for after reading the step, to provide the user time to complete it.  Current max pause time is 10 seconds.

## Using Audio Player Voice Directives

Once inside the skill, the user can utilize audio directives to navigate back and forth along the recipe's sequence of instructions.  
