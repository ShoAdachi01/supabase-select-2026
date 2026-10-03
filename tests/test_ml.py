import numpy as np
import pandas as pd
import pytest

from server.ml import inspect_frame, predict, sample_dataset, train_experiment


@pytest.fixture(scope="module")
def shipment_model():
    frame, _, _, target = sample_dataset("shipments")
    profile = inspect_frame(frame)
    features = [c["name"] for c in profile["columns"] if not c["excluded"] and c["name"] != target]
    model, result = train_experiment(frame, target, features, "classification", lambda *_: None)
    return model, result


def test_post_outcome_data_is_identified():
    frame, _, _, _ = sample_dataset("shipments")
    actual = next(c for c in inspect_frame(frame)["columns"] if c["name"] == "actual_delivery_days")
    assert actual["excluded"]
    assert "leakage" in actual["reason"]


def test_prediction_is_a_real_model_result(shipment_model):
    model, result = shipment_model
    output = predict(model, result, [result["example_input"]])
    assert output["predictions"][0]["value"] in result["labels"]
    assert sum(output["predictions"][0]["probabilities"].values()) == pytest.approx(1)
    assert output["tokens_used_for_prediction"] == 0
    assert result["test_score"] > result["baseline_score"]
    assert sum(result["splits"][s] for s in ("train", "validation", "test")) == 1600


def test_missing_required_input_is_rejected(shipment_model):
    model, result = shipment_model
    incomplete = dict(result["example_input"])
    del incomplete[result["features"][0]]
    with pytest.raises(ValueError, match="missing required fields"):
        predict(model, result, [incomplete])


def test_infinite_prediction_input_is_rejected(shipment_model):
    model, result = shipment_model
    row = dict(result["example_input"])
    row["distance_km"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        predict(model, result, [row])


def test_target_cannot_be_an_input_feature():
    frame, _, _, target = sample_dataset("shipments")
    with pytest.raises(ValueError, match="exclude the target"):
        train_experiment(frame, target, [target], "classification", lambda *_: None)


def test_final_holdout_does_not_change_selected_method():
    rng = np.random.default_rng(33)
    frame = pd.DataFrame(
        {"x": rng.uniform(-3, 3, 150), "date": pd.date_range("2020-01-01", periods=150).astype(str)}
    )
    frame["target"] = frame.x * 3 + rng.normal(0, 0.1, len(frame))
    model1, result1 = train_experiment(
        frame, "target", ["x"], "regression", lambda *_: None, "temporal", "date"
    )
    poisoned = frame.copy()
    poisoned.loc[120:, "target"] = 100000
    poisoned.loc[120:, "x"] = 90000
    model2, result2 = train_experiment(
        poisoned, "target", ["x"], "regression", lambda *_: None, "temporal", "date"
    )
    assert result1["selected_model"] == result2["selected_model"]
    assert [x["name"] for x in result1["leaderboard"]] == [
        x["name"] for x in result2["leaderboard"]
    ]
    # Parallel tree reductions can differ by machine-precision rounding.
    assert [x["score"] for x in result1["leaderboard"]] == pytest.approx(
        [x["score"] for x in result2["leaderboard"]], rel=1e-12, abs=1e-12
    )
    assert model1.predict(pd.DataFrame({"x": [1.0]}))[0] == pytest.approx(
        model2.predict(pd.DataFrame({"x": [1.0]}))[0]
    )
    assert result2["test_score"] > result1["test_score"] * 100


def test_chronological_split_does_not_cut_identical_timestamps():
    frame = pd.DataFrame(
        {"x": range(100), "target": np.arange(100) * 2, "date": ["2020-01-01"] * 100}
    )
    with pytest.raises(ValueError, match="distinct time periods"):
        train_experiment(frame, "target", ["x"], "regression", lambda *_: None, "temporal", "date")
