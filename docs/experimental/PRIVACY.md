# Privacy (experimental guided assistant)

Five capabilities stay separate. Turning one on does not turn the others on.

| Capability | What leaves the device |
| --- | --- |
| Built-in explanations | Nothing. No network. |
| Local model | Nothing. The model and the measurement stay on the device. A model is never downloaded unless you ask. |
| Cloud model, your API key | A sanitized diagnostic summary goes **directly** from this device to the provider you chose. ReverbScope does not receive the key and does not proxy the call. |
| Online lookup | A generic technical query, not a measurement. Off unless you enable it. This build does not crawl the web unless an endpoint is configured. |
| Help improve ReverbScope | Off by default. Opt-in usage, generic hardware compatibility, or anonymous crash category. |

## Never sent automatically

API keys, raw audio, impulse-response waveforms, session files, screenshots,
full logs, personal notes, home paths, usernames, exact location, room name,
serial numbers, or unique device identifiers. Configuring a key does not
enable telemetry. Enabling telemetry does not include the key.

## Privacy mode

`reverbscope --privacy-mode` blocks cloud models, online lookup, telemetry,
and crash upload for that run. Built-in explanations and an already
downloaded local model still work. A stored key is not deleted, and it is
not used.

## Payload

Cloud analysis defaults to Minimal: finding type, severity, confidence,
validity, and the necessary validated numbers. Detailed can add valid
octave-band summaries and a generic device model you typed. Audio and full
sessions require a separate explicit upload action, which normal explanation
does not perform. You can print the payload with
`reverbscope guided --result … --preview-payload`.

## First send

Adding a key does not allow analysis data to be sent. Cloud explanation has
its own switch, and the first send needs `--send-once` or
`--always-allow-sanitized`.
