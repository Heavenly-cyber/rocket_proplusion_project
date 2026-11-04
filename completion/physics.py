"""Independent ideal-flow references. All arguments use SI units."""
import math


def positive(**values):
    for name, value in values.items():
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")


def area_ratio(mach, gamma):
    positive(mach=mach, gamma=gamma - 1)
    return (2 / (gamma + 1) * (1 + (gamma - 1) * mach * mach / 2)) ** (
        (gamma + 1) / (2 * (gamma - 1))
    ) / mach


def exit_mach(epsilon, gamma):
    positive(epsilon=epsilon, gamma=gamma - 1)
    if epsilon < 1:
        raise ValueError("Ae/At must be >= 1")
    if epsilon == 1:
        return 1.0
    lo, hi = 1.0, 2.0
    while area_ratio(hi, gamma) < epsilon:
        hi *= 2
        if hi > 1024:
            raise ValueError("Supersonic root is outside the supported interval")
    for _ in range(120):
        mid = (lo + hi) / 2
        if area_ratio(mid, gamma) < epsilon:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def mass_flow(p0, T0, At, gamma, R):
    positive(p0=p0, T0=T0, At=At, gamma=gamma - 1, R=R)
    return p0 * At / math.sqrt(T0) * math.sqrt(gamma / R) * (
        2 / (gamma + 1)
    ) ** ((gamma + 1) / (2 * (gamma - 1)))


def thrust(mdot, Ve, pe, pa, Ae):
    positive(mdot=mdot, Ve=Ve, Ae=Ae)
    if any(not math.isfinite(v) or v < 0 for v in (pe, pa)):
        raise ValueError("Pressures must be finite and nonnegative")
    return mdot * Ve + (pe - pa) * Ae


def state(p0, T0, At, gamma, R, epsilon, pa=0.0):
    positive(p0=p0, T0=T0, At=At, gamma=gamma - 1, R=R)
    mach = exit_mach(epsilon, gamma)
    factor = 1 + (gamma - 1) * mach * mach / 2
    Te = T0 / factor
    pe = p0 / factor ** (gamma / (gamma - 1))
    Ve = mach * math.sqrt(gamma * R * Te)
    Ae = At * epsilon
    mdot = mass_flow(p0, T0, At, gamma, R)
    rho = pe / (R * Te)
    F = thrust(mdot, Ve, pe, pa, Ae)
    return dict(Me=mach, Te=Te, pe=pe, Ve=Ve, Ae=Ae, mdot=mdot, F=F,
                momentum_thrust=mdot * Ve, pressure_thrust=(pe-pa)*Ae,
                Isp=F/(mdot*9.80665), Cf=F/(p0*At),
                continuity_relative_error=abs(rho*Ve*Ae-mdot)/mdot,
                epsilon=epsilon)


def reference(case):
    kind, values = case["reference"]["kind"], case["reference"]["inputs"]
    if kind == "mass_flow":
        return mass_flow(**values), "kg/s"
    if kind == "thrust":
        return thrust(**values), "N"
    if kind == "velocity":
        return state(**values)["Ve"], "m/s"
    return None, None


def verification():
    from scipy.optimize import brentq
    rows = []
    for gamma in (1.15, 1.2, 1.3, 1.4, 1.67):
        for epsilon in (1.01, 1.5, 2, 4, 8, 20, 50):
            root = exit_mach(epsilon, gamma)
            independent = brentq(lambda x: area_ratio(x, gamma)-epsilon, 1+1e-12, 100)
            result = state(1e6, 900, 0.001, gamma, 287, epsilon, 1e5)
            if abs(root-independent) > 1e-9 or result["continuity_relative_error"] > 1e-10:
                raise AssertionError("Reference cross-check failed")
            rows.append(dict(gamma=gamma, epsilon=epsilon, bisection=root,
                             scipy_brentq=independent, continuity=result["continuity_relative_error"]))
    worked = state(1e6, 900, 0.001, 1.4, 287, 1.6875, 1e5)
    assert abs(area_ratio(2, 1.4) - 1.6875) < 1e-12
    assert abs(worked["Te"] - 500) < 1e-9
    # Independent energy equation and direct supplied-state thrust identity.
    energy_speed = math.sqrt(2*1.4/(1.4-1)*287*900*(1-(worked["pe"]/1e6)**((1.4-1)/1.4)))
    assert abs(energy_speed - worked["Ve"]) < 1e-9
    assert thrust(2, 1000, 200000, 100000, .01) == 3000
    return dict(status="passed", independent_root_checks=rows, worked_example=worked,
                checks=["Mach-two analytic identity", "supersonic brentq cross-check",
                        "mass continuity", "independent energy equation", "pressure thrust"])
