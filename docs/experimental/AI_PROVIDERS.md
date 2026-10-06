# AI providers (experimental, bring your own key)

Not part of the 0.5 stable or release-candidate feature set.

## Where you configure it

Desktop: Settings → Guided assistant (智能诊断助手). The default engine is
built-in offline explanations. Choosing a cloud service, or saving a key,
does not by itself send a measurement.

Command line, still without putting the key in a file:

```text
reverbscope guided --result session-folder --engine cloud --provider openai \
  --model <model-you-choose> --enable-cloud --send-once
```

The key is read from the system credential store for that provider, or from
`REVERBSCOPE_API_KEY` for this process only. That variable is not written to
settings, logs, or the report. If no key is available, nothing is sent.

`--privacy-mode` does not delete the key and does not use it.

## Add a key

The settings object has no key field. A key is stored only through
`CredentialVault`:

- system credential store, when `keyring` is installed and actually opens a backend
- this process only
- or cancel

If the system store is unavailable, the key is **not** written to
`guided_settings.json` or any other file.

The interface offers replace, remove, and test connection. It does not show
the key. Revealing it requires a second explicit confirmation.

## What a test connection sends

A one-line request that asks the provider to reply with a single word. It
does not include a measurement, audio, room, hardware report, or notes.

## What an explanation may send

Only after cloud explanation is enabled **and** you send once or always allow
sanitized summaries. The body is built by `CloudContextBuilder`. Preview it
before sending. The reply is checked by the explanation validator; a sentence
that invents a number, repairs an invalid metric, or names a surface is
replaced by the built-in text.

Your provider may charge you. If the response reports token counts, they are
shown. This program does not guess a price.

A custom base URL must be acknowledged. That server sees whatever you agreed
to send. ReverbScope does not vouch for it.

## Remove a key

Delete it from the credential store. Exporting settings omits credentials.
A session may record the provider type and model id, never the key.

## Turn cloud analysis off

Set the explanation engine back to built-in, disable cloud explanation, or
run with `--privacy-mode`. A failure (bad key, rate limit, timeout, missing
model, malformed reply) falls back to the built-in explanation and does not
affect the measurement.
