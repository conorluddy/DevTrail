# DevTrail: CLI work logging tool

This is a simple CLI tool I use for logging work from the terminal throughout the workday. When you're juggling a lot of tasks it can be easy to forget all of the things you've worked on. I find this approach one of the quickest ways to track work/ideas/thoughts/todos etc.

Logs get committed to the git repo automatically when you create them so I'd recommend keeping your cloned repo private.

Feel free to clone this and tweak it to suit your own workflow.

## Features

- Easily log entries from the command line
- Add tags for organization
- Automatically timestamp entries
- Store logs in a structured JSON format
- Keep a Git history of your logs
- Use the JSON for later use in a UI or LLM 

- The `-m` flag is required and is used to specify your log message.
- The `-t` flag is optional and can be used to add comma-separated tags. 
- The `-y` flag is optional and will log the datetime as 6PM the previous day (for stuff you forgot).

1. The script will:
- Add a timestamped entry to the `log.json` file.
- Commit the changes to Git.
- Push the changes to the 'main' branch.

## Setup

To use this script:

Save it as logger.sh in a directory of your choice.

Make it executable: chmod +x logger.sh

Set up an alias in your .bashrc or .zshrc:

e.g. (you can alias it as whatever you like)

alias devlog='/path/to/logger.sh'

Now you can use it like this:

devlog -m "Implemented new feature" -t "development,feature,project-x"

## Roadmap

- Let this run in the background and prompt you for updates if it hasn't been logged to in X hours.
- Use something like Gum to make the interface prettier.
- Integrate with an LLM so you can query your logs from the CLI.