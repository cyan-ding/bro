"use client";
import { useEffect } from "react";
import { useAuthStore } from "@/store/useAuthStore";
import { supabase } from "@/lib/supabase";

export default function AuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { setUser, setAuthToken } = useAuthStore();

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === "SIGNED_IN" && session) {
        setUser({
          id: session.user.id,
          email: session.user.email || null,
          name: session.user.user_metadata?.full_name || null,
          avatar: session.user.user_metadata?.avatar_url || null,
        });
      }
      setAuthToken(session?.access_token || null);
      if (event === "SIGNED_OUT" || !session) {
        setUser(null);
      }
    });

    return () => subscription.unsubscribe();
  }, [setAuthToken, setUser]);

  return <>{children}</>;
}
