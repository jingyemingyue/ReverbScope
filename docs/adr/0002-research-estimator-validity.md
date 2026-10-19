# Research estimators: preserve validity and physical units

This decision follows GUIDELINES.zh-CN.md §3 D11, §4 C1/C2/C12 and §6.
It applies to the experimental algorithm work in PR #74, independently of
the GUI redesign. Status: draft, for maintainer review.

## Decision

- Preserve the existing fast-decay truncation-sensitivity test and its
  UNRELIABLE result. Noise subtraction must not turn a rejected floor
  estimate into an apparently valid EDT. Port the conservative eligibility
  guard already present in PR #74 (originally from PR #72): no truncation problem and more than 40 dB of dynamic
  range. This is a heuristic eligibility rule, not an ISO validity threshold.
  Subtraction remains disabled by default, following ADR 0003 and ADR 0004;
  this eligibility rule applies only to explicit opt-in.
- For a power model `A exp(-t/tau)`, T60 is `tau * ln(10^6)`, since power
  falls by a factor of one million in 60 dB. The amplitude constant
  `ln(1000)` is inappropriate for this model.
- Normalize input power before nonlinear fitting and restore amplitude and
  noise units afterwards. Preserve each model's order when a lower-order
  fit fails; failed candidates keep an infinite BIC slot.
- The LP polynomial convention is `1 + a[1] z^-1 + ...`. Its coefficients
  solve the Yule-Walker system with a negative right-hand side. Update the
  recursion from the previous coefficient vector, not partially updated
  values. Compute only the required `p+1` autocorrelation lags: O(N*p)
  work instead of a full O(N^2) correlation.
- Reject negative or non-finite power. A zero-power model fit is withheld.

## Evidence and limits

`tests/unit/test_algorithm_methods.py` contains independent checks for the
60 dB energy drop, a known 0.8 s exponential at three power scales, failed
model-order candidates, invalid powers, an analytic truncation point and
an AR(1) process's known prediction coefficients. Existing decay validity
assertions remain intact.

These checks are synthetic and automated. They do not establish low-SNR
accuracy on measured rooms, ISO compliance, or modal-estimator accuracy.
The function named `fit_bayesian_decay` remains for API continuity; it is
deterministic NLS with BIC, not posterior inference, and provides no
parameter-uncertainty estimate. No default GUI or file format is extended.

## Sources

- The existing project measurement method:
  [MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md).
- MathWorks' [IEC 60268-16 verification example](https://www.mathworks.com/help/audio/ug/speech-transmission-index-iec60268-16-edition-5-compliance.html),
  indirect-method analytic decay: power uses `ln(10^6)`.
- SciPy [solve_toeplitz documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.solve_toeplitz.html)
  describes the Levinson-Durbin Toeplitz solve. No third-party source was copied.
