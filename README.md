# OptUncertain

This entry point now runs MatterSim in manual RGB exploration mode only. It does
not enable depth images or call a multimodal model.

## Python 3.6.9 notes

This project is adjusted to run on Python 3.6.9.

If you use Python 3.6, install the backport of dataclasses:

    pip install dataclasses

SigLIP encoders require:

    pip install torch transformers
