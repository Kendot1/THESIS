"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { Language, TranslationKey, getTranslation } from "./translations";

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: TranslationKey) => string;
  isTransitioning: boolean;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");
  const [isTransitioning, setIsTransitioning] = useState(false);
  const transitionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load language from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem("foodcast_language") as Language;
      if (stored === "en" || stored === "tl") {
        setLanguageState(stored);
      }
    } catch (e) {
      // Ignore
    }
  }, []);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (transitionTimer.current) clearTimeout(transitionTimer.current);
    };
  }, []);

  const setLanguage = useCallback((lang: Language) => {
    // Start transitioning
    setIsTransitioning(true);
    if (transitionTimer.current) clearTimeout(transitionTimer.current);

    // Apply language change after a brief delay so the skeleton renders first
    transitionTimer.current = setTimeout(() => {
      setLanguageState(lang);
      try {
        localStorage.setItem("foodcast_language", lang);
      } catch (e) {
        // Ignore
      }

      // End transitioning after another brief moment for re-render
      transitionTimer.current = setTimeout(() => {
        setIsTransitioning(false);
      }, 150);
    }, 50);
  }, []);

  const t = useCallback(
    (key: TranslationKey) => {
      return getTranslation(key, language);
    },
    [language]
  );

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, isTransitioning }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error("useLanguage must be used within a LanguageProvider");
  }
  return context;
}
