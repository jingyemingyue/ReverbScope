# On-device explanation model (experimental)

Not part of the 0.5 stable or release-candidate feature set. The measurement
core does not import it.

## What was trained

`guided-clause-v1` is a small model trained with gradient descent on the
offline catalog only. No audio, no user measurement, and no downloaded base
model are in the training set.

It does not write sentences freely. Each step picks the next approved catalog
clause for that finding and language, or stops. Length (concise, balanced,
detailed) chooses the plan. Measurement numbers are not inputs and are not
in the vocabulary. A safety probe, plus the existing explanation validator,
rejects digits and known unsafe phrases such as naming a desk as the cause
or lifting a safety ground.

Other languages still fall back to the English catalog. The model does not
pretend to be translated.

## Install

The file ships with this experimental build but is not used until you install
it. Nothing is downloaded.

Desktop: Settings → Guided assistant → Install the on-device model.

Command line:

```text
reverbscope guided --result session-folder --install-local-model
```

That copies the file, checks it against the catalog fingerprint, and selects
the local engine. Built-in explanations remain the default if you do not do
this. Privacy mode still allows this model. It does not allow the cloud.

If the catalog changes, the fingerprint no longer matches and the model
refuses to load. Retrain with:

```text
python -m reverbscope.experimental.guided.local.train
```
