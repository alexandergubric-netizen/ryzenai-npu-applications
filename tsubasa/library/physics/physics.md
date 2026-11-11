# Physics reference

## SI units and prefixes
- Base units: metre (m), kilogram (kg), second (s), ampere (A), kelvin (K), mole (mol), candela (cd).
- Derived: newton N = kg m s⁻², joule J = N m, watt W = J s⁻¹, pascal Pa = N m⁻², coulomb C = A s, volt V = W A⁻¹, ohm Ω = V A⁻¹, farad F = C V⁻¹, tesla T = N A⁻¹ m⁻¹, hertz Hz = s⁻¹.
- Prefixes: p 10⁻¹², n 10⁻⁹, µ 10⁻⁶, m 10⁻³, c 10⁻², k 10³, M 10⁶, G 10⁹, T 10¹².
- Conversions: 1 kWh = 3.6 MJ; 1 eV = 1.602176634 × 10⁻¹⁹ J; 1 km/h = 0.2778 m/s; 1 atm = 101325 Pa; 1 cal = 4.184 J; 1 inch = 2.54 cm.

## Constants
- g = 9.81 m s⁻² (standard 9.80665); G = 6.674 × 10⁻¹¹ N m² kg⁻²; c = 2.998 × 10⁸ m s⁻¹.
- e = 1.602 × 10⁻¹⁹ C; m_e = 9.109 × 10⁻³¹ kg; m_p = 1.673 × 10⁻²⁷ kg; h = 6.626 × 10⁻³⁴ J s; ħ = 1.055 × 10⁻³⁴ J s.
- ε₀ = 8.854 × 10⁻¹² F m⁻¹; k = 1/(4πε₀) = 8.988 × 10⁹ N m² C⁻²; µ₀ = 1.2566 × 10⁻⁶ N A⁻².
- k_B = 1.381 × 10⁻²³ J K⁻¹; σ (Stefan–Boltzmann) = 5.670 × 10⁻⁸ W m⁻² K⁻⁴; R = 8.314 J mol⁻¹ K⁻¹.
- Earth: mass 5.97 × 10²⁴ kg, radius 6.371 × 10⁶ m; Sun–Earth distance 1.496 × 10¹¹ m; speed of sound in air ≈ 343 m s⁻¹ at 20 °C.

## Kinematics (constant acceleration)
- v = v₀ + a t; s = v₀ t + ½ a t²; v² = v₀² + 2 a s; s = (v₀ + v) t / 2.
- Projectile (no air resistance): horizontal x = v₀ cos θ · t; vertical y = v₀ sin θ · t − ½ g t²; range R = v₀² sin 2θ / g; maximum height H = v₀² sin² θ / (2g).
- Circular motion: v = 2πr / T; centripetal acceleration a = v² / r = ω² r; ω = 2π f.

## Dynamics
- Newton: ΣF = m a; weight W = m g; friction F = µ N; spring F = −k x.
- Momentum p = m v; impulse J = F Δt = Δp; momentum is conserved in collisions; in elastic collisions kinetic energy is conserved too.
- Gravity F = G m₁ m₂ / r²; orbital speed (orbital velocity) v = √(GM / r); escape speed (escape velocity) v = √(2GM / r); Kepler: T² ∝ r³.
- Escape velocity of Earth ≈ 11.2 km/s, of the Moon ≈ 2.4 km/s; low Earth orbit speed ≈ 7.8 km/s; g on the Moon ≈ 1.62 m/s².
- Torque τ = r F sin θ; moment of inertia: point mass m r², solid disc ½ m r², solid sphere ⅖ m r², rod about its centre (1/12) m L².
- Rotational: τ = I α; angular momentum L = I ω; rotational kinetic energy ½ I ω².

## Energy and power
- Work W = F s cos θ; kinetic energy E_k = ½ m v²; potential energy E_p = m g h; spring energy ½ k x².
- Power P = W / t = F v; efficiency η = useful output / input.
- Pressure p = F / A; hydrostatic p = ρ g h; buoyancy F = ρ_fluid V g; continuity A₁v₁ = A₂v₂; Bernoulli p + ½ρv² + ρgh = constant.

## Oscillations and waves
- Simple harmonic motion: x = A cos(ωt + φ); spring T = 2π√(m/k); pendulum T = 2π√(L/g) (small angles).
- Waves: v = f λ; T = 1 / f; string v = √(T / µ); standing waves on a string λ_n = 2L / n.
- Doppler (sound): f' = f (v + v_observer) / (v − v_source) with motion towards each other positive.
- Intensity level β = 10 log₁₀(I / 10⁻¹² W m⁻²) dB; intensity falls as 1/r² from a point source.

## Electricity and magnetism
- Coulomb F = k q₁ q₂ / r²; field E = F / q = k q / r²; potential V = k q / r; energy W = q V.
- Ohm's law V = I R; power P = V I = I² R = V² / R; resistivity R = ρ L / A.
- Series: R = R₁ + R₂; parallel: 1/R = 1/R₁ + 1/R₂. Capacitors: C = Q / V, series 1/C = Σ 1/C_i, parallel C = Σ C_i, energy ½ C V², RC time constant τ = R C.
- Kirchhoff: currents into a node sum to zero; voltages around a loop sum to zero.
- Magnetic force on a charge F = q v B sin θ; on a wire F = B I L sin θ; field of a long wire B = µ₀ I / (2π r); solenoid B = µ₀ n I.
- Faraday: emf = −N dΦ/dt with Φ = B A cos θ; transformer V_s / V_p = N_s / N_p. AC: V_rms = V_peak / √2.

## Thermodynamics
- Heat Q = m c ΔT; latent heat Q = m L (water: L_f = 334 kJ/kg, L_v = 2260 kJ/kg; c = 4186 J kg⁻¹ K⁻¹).
- First law ΔU = Q − W (W done by the gas); ideal gas p V = n R T = N k_B T; mean kinetic energy per molecule (3/2) k_B T.
- Efficiency of a heat engine η = W / Q_h ≤ 1 − T_c / T_h (Carnot, kelvin). Entropy change ΔS = Q / T for a reversible process.
- Conduction P = k A ΔT / d; radiation P = ε σ A T⁴; thermal expansion ΔL = α L ΔT.

## Optics
- Reflection: angle of incidence = angle of reflection. Refraction (Snell) n₁ sin θ₁ = n₂ sin θ₂; n = c / v (water 1.33, glass ≈ 1.5).
- Critical angle sin θ_c = n₂ / n₁. Thin lens and mirror: 1/f = 1/d_o + 1/d_i; magnification m = −d_i / d_o; lens power P = 1/f (dioptres, f in m).
- Double slit: bright fringes d sin θ = m λ; fringe spacing Δy = λ L / d. Diffraction grating d sin θ = m λ.

## Modern physics
- Photon energy E = h f = h c / λ; photoelectric effect E_k,max = h f − φ; de Broglie λ = h / p.
- Mass–energy E = m c²; relativistic factor γ = 1/√(1 − v²/c²); time dilation Δt = γ Δt₀; length contraction L = L₀ / γ.
- Hydrogen levels E_n = −13.6 eV / n². Radioactive decay N = N₀ e^(−λt), half-life t½ = ln 2 / λ, activity A = λ N.
- Heisenberg: Δx Δp ≥ ħ / 2.

## Problem-solving checklist
1. Sketch the situation and list knowns and unknowns with units. 2. Pick the principle (forces, energy, momentum, conservation laws). 3. Solve symbolically first. 4. Substitute with units. 5. Check units, sign and order of magnitude (e.g. a car's acceleration should be a few m/s², not thousands).
