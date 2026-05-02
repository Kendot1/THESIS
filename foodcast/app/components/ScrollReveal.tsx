"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";

interface ScrollRevealProps {
  children: ReactNode;
  className?: string;
  animation?: "fade-up" | "fade-in" | "slide-left" | "slide-right" | "scale-in";
  delay?: number;
  threshold?: number;
  once?: boolean;
}

const animationClasses = {
  "fade-up": "animate-fade-in-up",
  "fade-in": "animate-fade-in",
  "slide-left": "animate-slide-left",
  "slide-right": "animate-slide-right",
  "scale-in": "animate-scale-in",
};

const listeners = new WeakMap<Element, (isIntersecting: boolean) => void>();
let sharedObserver: IntersectionObserver | null = null;

function getObserver() {
  if (typeof window === "undefined") return null;
  if (!sharedObserver) {
    sharedObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const callback = listeners.get(entry.target);
          if (callback) callback(entry.isIntersecting);
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -20px 0px" }
    );
  }
  return sharedObserver;
}

const ScrollReveal = ({
  children,
  className = "",
  animation = "fade-up",
  delay = 0,
  once = true,
}: ScrollRevealProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = getObserver();
    if (!observer) return;

    listeners.set(el, (isIntersecting) => {
      if (isIntersecting) {
        setIsVisible(true);
        if (once) {
          observer.unobserve(el);
          listeners.delete(el);
        }
      } else if (!once) {
        setIsVisible(false);
      }
    });

    observer.observe(el);

    return () => {
      observer.unobserve(el);
      listeners.delete(el);
    };
  }, [once]);

  return (
    <div
      ref={ref}
      className={`${className} ${isVisible ? animationClasses[animation] : "opacity-0"}`}
      style={{ animationDelay: isVisible ? `${delay}ms` : undefined }}
    >
      {children}
    </div>
  );
};

export default ScrollReveal;
