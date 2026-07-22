/**
 * Single source of truth for "are we paired", shared between the root
 * layout (which redirects to /onboarding when not paired) and the
 * onboarding screen itself (which flips this the moment pairing succeeds).
 * Without this, the two would read pairing state independently and could
 * fight each other's navigation right after a successful pair.
 */
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';
import { getPairing } from './pairing';

type PairingContextValue = {
  isPaired: boolean;
  isLoading: boolean;
  markPaired: () => void;
  markUnpaired: () => void;
};

const PairingContext = createContext<PairingContextValue | null>(null);

export function PairingProvider({ children }: { children: ReactNode }) {
  const [isPaired, setIsPaired] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    getPairing().then((info) => {
      setIsPaired(!!info);
      setIsLoading(false);
    });
  }, []);

  return (
    <PairingContext.Provider
      value={{
        isPaired,
        isLoading,
        markPaired: () => setIsPaired(true),
        markUnpaired: () => setIsPaired(false),
      }}
    >
      {children}
    </PairingContext.Provider>
  );
}

export function usePairingContext(): PairingContextValue {
  const ctx = useContext(PairingContext);
  if (!ctx) throw new Error('usePairingContext must be used within a PairingProvider');
  return ctx;
}
