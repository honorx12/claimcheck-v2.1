import type { ComponentType, ReactNode } from 'react'
import PrismaticBurst from './PrismaticBurst'
import Iridescence from './Iridescence'

// The two animation files use @ts-nocheck, so we give them a loose prop type here.
type Loose = ComponentType<Record<string, unknown>>
const Burst = PrismaticBurst as unknown as Loose
const Irid = Iridescence as unknown as Loose

// Brand: primary #0B5563 (deep teal). Palette below stays in the teal/cyan family.
const BURST_COLORS = ['#0B5563', '#0E9AA7', '#2DD4BF', '#A5F3FC']

// Landing hero: dark teal panel + prismatic rays. Text sits in the dimmed centre.
export function Hero({ children }: { children: ReactNode }) {
  return (
    <section className="relative isolate overflow-hidden rounded-2xl bg-[#06232A] text-white">
      <div className="absolute inset-0 -z-10 pointer-events-none" aria-hidden="true">
        <Burst
          colors={BURST_COLORS}
          animationType="rotate3d"
          intensity={2}
          speed={0.6}
          zoom={1}
          rayCount={8}
          rayWidth={1}
          centerFade={1.3}
          glow={0.35}
          grain={0.3}
          quality="medium"
          mouseInteraction
          clickBurst
          intro
        />
      </div>
      {/* Scrim keeps text readable even when rays pass behind it */}
      <div
        className="absolute inset-0 -z-10 pointer-events-none"
        aria-hidden="true"
        style={{ background: 'radial-gradient(ellipse at center, rgba(6,35,42,0.8) 0%, rgba(6,35,42,0) 70%)' }}
      />
      <div className="mx-auto max-w-2xl px-6 py-16 sm:py-24 text-center">{children}</div>
    </section>
  )
}

// Login/signup: soft teal iridescence behind a solid white form card.
export function AuthBackdrop({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate overflow-hidden rounded-2xl bg-[#CFE6EA] min-h-[28rem] grid place-items-center p-4 sm:p-10">
      <div className="absolute inset-0 -z-10 pointer-events-none" aria-hidden="true">
        <Irid color="#5FB3BF" brightness={1.2} saturation={1.1} speed={0.8} amplitude={0.1} stir={0.5} sheen={0.3} resolution={0.75} mouseReact clickSwirl />
      </div>
      <div className="w-full max-w-sm rounded-xl border border-line bg-surface p-6 shadow-lg">{children}</div>
    </div>
  )
}
