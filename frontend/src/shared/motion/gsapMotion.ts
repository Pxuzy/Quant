import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

type MotionTarget = gsap.TweenTarget;

type FadeInUpOptions = {
  duration?: number;
  stagger?: number;
  y?: number;
  delay?: number;
};

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

export { gsap, useGSAP };

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

export function fadeInUp(targets: MotionTarget, options: FadeInUpOptions = {}) {
  if (prefersReducedMotion()) {
    gsap.set(targets, { opacity: 1, y: 0, clearProps: 'transform,opacity' });
    return;
  }

  gsap.fromTo(
    targets,
    { opacity: 0, y: options.y ?? 10 },
    {
      opacity: 1,
      y: 0,
      delay: options.delay ?? 0,
      duration: options.duration ?? 0.32,
      stagger: options.stagger ?? 0,
      ease: 'power1.out',
      overwrite: 'auto',
      clearProps: 'transform,opacity',
    },
  );
}

export function pulseFeedback(targets: MotionTarget, duration = 0.18) {
  if (prefersReducedMotion()) {
    gsap.set(targets, { opacity: 1, scale: 1, clearProps: 'transform,opacity' });
    return;
  }

  gsap.fromTo(
    targets,
    { opacity: 0.86, scale: 0.985 },
    {
      opacity: 1,
      scale: 1,
      duration,
      ease: 'power1.out',
      overwrite: 'auto',
      clearProps: 'transform,opacity',
    },
  );
}

/**
 * Animate a number from 0 to target value — TradingView-style tick animation.
 * Usage: animateNumber({ from: 0, to: 3876.78, selector: '#price-600519' })
 */
export function animateNumber(
  selector: string,
  targetValue: number,
  options: { duration?: number; from?: number; prefix?: string; suffix?: string; decimals?: number } = {},
) {
  if (prefersReducedMotion()) {
    gsap.set(selector, { innerText: targetValue.toFixed(options.decimals ?? 2) });
    return;
  }

  const el = typeof selector === 'string' ? document.querySelector(selector) : selector;
  if (!el) return;

  const { duration = 0.6, from = 0, prefix = '', suffix = '', decimals = 2 } = options;

  gsap.fromTo(
    el,
    { textContent: from.toFixed(decimals) },
    {
      textContent: targetValue.toFixed(decimals),
      duration,
      ease: 'power2.out',
      snap: { textContent: 10 ** -decimals },
      overwrite: 'auto',
      onUpdate() {
        const val = parseFloat(el.textContent || '0');
        el.textContent = `${prefix}${val.toFixed(decimals)}${suffix}`;
      },
    },
  );
}
