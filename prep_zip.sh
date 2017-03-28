#!/bin/bash

declare -a AGFILES=("lambda_function.py"
  "recipes.json");

zip -u -r recipe_reader.zip "${AGFILES[@]}"
