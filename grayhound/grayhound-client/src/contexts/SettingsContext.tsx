// src/contexts/SettingsContext.tsx
import React, { createContext, useContext, useState } from 'react';

interface SettingsContextType {
  language: string;
  setLanguage: (lang: string) => void;
}

const SettingsContext = createContext<SettingsContextType>({
  language: 'en',
  setLanguage: () => {},
});

export const useSettings = () => useContext(SettingsContext);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguage] = useState(() => {
    return localStorage.getItem('grayhound_language') || 'en';
  });

  const updateLanguage = (newLang: string) => {
    setLanguage(newLang);
    localStorage.setItem('grayhound_language', newLang);
  };

  return (
    <SettingsContext.Provider value={{ language, setLanguage: updateLanguage }}>
      {children}
    </SettingsContext.Provider>
  );
};