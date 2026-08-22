import numpy as np
from kytos.features.basal import extract_basal_context
from kytos.models.layer_a import ContextConditionedTransfer, MeanShiftTransfer
from kytos.models.layer_b import AdditiveTransportSampler


def test_layer_a_mean_shift_transfer():
    genes = ["ACTB", "GAPDH", "ISG15"]
    X = np.array([[2.0, 3.0, 1.0], [2.2, 3.1, 0.9]])
    ctx = extract_basal_context(X, genes)

    model = MeanShiftTransfer()
    delta = model.predict_delta("ISG15", ctx)
    assert delta.shape == (3,)
    assert delta[2] == -2.5  # ISG15 is knocked down
    assert delta[0] == 0.0  # unperturbed genes stay 0


def test_layer_a_context_conditioned_transfer():
    genes = ["ACTB", "GAPDH", "MYC"]
    X = np.array([[10.0, 8.0, 0.1], [9.8, 8.2, 0.2]])
    ctx = extract_basal_context(X, genes)

    model = ContextConditionedTransfer()
    delta = model.predict_delta("MYC", ctx)
    assert delta.shape == (3,)
    assert delta[2] < 0.0  # MYC knocked down


def test_layer_b_additive_transport_sampler():
    X_basal = np.array([[5.0, 4.0, 3.0], [5.2, 3.8, 3.1], [4.9, 4.1, 2.9]])
    delta = np.array([0.0, 0.0, -2.0])

    sampler = AdditiveTransportSampler(noise_scale=0.01)
    samples = sampler.sample_cells(X_basal, delta, n_samples=5, seed=123)

    assert samples.shape == (5, 3)
    assert (samples >= 0.0).all()
    # MYC expression in samples should be significantly lower than basal
    assert samples[:, 2].mean() < X_basal[:, 2].mean() - 1.5
