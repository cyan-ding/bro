"use client"
import { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/store/useAuthStore";
import { createClient } from "@supabase/supabase-js";
import { NavMenu } from "@/components/ui/navbar";

const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);


export default function AuthProvider({ children }: { children: React.ReactNode }) {


    const { user, setUser, setAuthToken } = useAuthStore();


    useEffect(() => {
        supabase.auth.onAuthStateChange(async (event, session) => {
            if (event === "SIGNED_IN" && session) {
                setUser({
                    id: session.user.id,
                    email: session.user.email || null,
                    name: session.user.user_metadata?.full_name || null,
                    avatar: session.user.user_metadata?.avatar_url || null,
                });
            }
            setAuthToken(session?.access_token || null)
            if (event === "SIGNED_OUT" || !session) {
                setUser(null);
            }
        });
    }, [setAuthToken, setUser]);


    return (
        <div>
            <NavMenu
                onGoogleSignIn={() =>
                    supabase.auth.signInWithOAuth({
                        provider: "google",
                    })
                }
                onGoogleSignOut={() => supabase.auth.signOut()}
                user={user}
            />

            {children}
        </div>
    )
}