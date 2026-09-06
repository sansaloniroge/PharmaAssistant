# Generates docs/demo.gif. Requires the API running locally against the
# real farmacia_carmen_sanjuan tenant (see README "How to run it").
# Run: vhs docs/demo.tape

Output docs/demo.gif

Set Shell "bash"
Set FontSize 17
Set Width 1280
Set Height 600
Set Theme "Dracula"
Set TypingSpeed 8ms
Set Padding 20

Type "# Real product catalog, real OpenAI calls, budget parsed deterministically:"
Enter
Sleep 500ms

Type `curl -s -X POST "localhost:8080/answer?client_id=farmacia_carmen_sanjuan" -H "x-api-key: demo_key_farmacia_carmen_sanjuan" -H "content-type: application/json" -d '{"message": "I want a vitamin C serum, budget under 30 euros"}' | jq -r '"\(.answer | split("\n\n")[0:2] | join("\n\n"))\n\nSources: \(.sources | join(", "))"'`
Enter
Sleep 7s

Type "# A medical term (pregnancy) triggers a safety note automatically:"
Enter
Sleep 500ms

Type `curl -s -X POST "localhost:8080/answer?client_id=farmacia_carmen_sanjuan" -H "x-api-key: demo_key_farmacia_carmen_sanjuan" -H "content-type: application/json" -d '{"message": "I am pregnant and have melasma spots, what is safe to use?"}' | jq -r '"\(.answer | split("\n\n")[0:2] | join("\n\n"))\n\nSources: \(.sources | join(", "))"'`
Enter
Sleep 7s
