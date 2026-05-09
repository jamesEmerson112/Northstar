from tzafon import Lightcone

client = Lightcone()

for event in client.agent.tasks.start_stream(
    instruction="Go to wikipedia.org, search for 'Alan Turing', and tell me the first sentence of the article",
    kind="desktop",
):
    print(event)
