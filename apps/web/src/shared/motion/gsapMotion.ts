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
