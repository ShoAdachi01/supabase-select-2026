# Forge: submission and demo

## One-line pitch

Forge turns a CSV into a tested prediction tool that an agent can call instead of guessing a number with language-model tokens.

## The problem

An operations assistant may know how to explain delivery risk but lack a validated way to predict it from the company's own data. Connecting data, preparing inputs, evaluating a model, and exposing it as an authenticated tool currently require several separate steps. Forge makes that workflow visible and repeatable.

## Two-minute demo

1. Open the skill library and select **Will this shipment be late?** Explain that this is simulated operational data, explicitly labeled in the interface.
2. Show the chosen target and inputs. Point out the excluded `actual_delivery_days` field: it is unavailable before delivery and could leak the outcome. Missing warehouse values are imputed using training rows only.
3. Click **Train & evaluate**. Show the saved experiment trace and the baseline, logistic regression, and random forest comparison. Selection uses validation data; the final metric uses a separate test set.
4. Click **Use this skill**, change the warehouse load or weather, and run an actual prediction. Show the model result, inference time, and zero language-model tokens for this prediction.
5. Save a known actual outcome. Explain that it is stored for review and does not silently change the model.
6. Open **Agent connection**, test discovery, and show the generated MCP configuration. Run `npm run test:mcp` in a terminal to demonstrate an official MCP client discovering and executing a trained tool on the public wine dataset.
7. Return to the library and refresh: the authenticated workspace, dataset, and experiment remain persisted in Supabase.

If time allows, upload a CSV or try the energy regression sample to show that the workflow supports more than one hardcoded target.

## Technical substance

Supabase Auth creates the workspace; Postgres saves datasets, runs, and predictions; private Storage keeps artifacts; Realtime updates experiments; RLS isolates users. A Python worker fits real scikit-learn pipelines. REST and MCP expose the selected model with a generated input schema.

## Honest boundaries

This is a working tabular prediction workflow. It does not invent a new AutoML algorithm or implement a universal model marketplace. There is no automatic feedback-driven retraining or payment system yet. Optional language-model planning requires a configured key; the default demo labels its schema-guided setup accurately.

## Inspiration

Our qualitative reading of recent Hack the North projects favored concrete execution with visible checks: [CADEX](https://devpost.com/software/cadex) generates CAD with geometry checks, [Reflex](https://devpost.com/software/reflex-e0jkih) connects agent commands to a physical glove, and [Signal](https://devpost.com/software/temp-project-0sp3zv) presents evidence-backed research. Forge applies that idea to measurable predictions: show the inputs, compare methods, then expose an executable capability. This is an interpretation of those examples, not a statistical survey of submissions.
