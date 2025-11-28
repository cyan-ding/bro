"use client";

import * as React from "react";
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu";

import { Button } from "./button";
import { AuthError, OAuthResponse } from "@supabase/supabase-js";
import { User } from "@/store/useAuthStore";

interface NavBarProps {
  onGoogleSignIn: () => Promise<OAuthResponse>;
  onGoogleSignOut: () => Promise<{
    error: AuthError | null;
  }>;
  user: User | null;
}

export function NavigationMenuDemo({
  user,
  onGoogleSignIn,
  onGoogleSignOut,
}: NavBarProps) {
  return (
    <NavigationMenu>
      <NavigationMenuList className="flex-wrap">
        <NavigationMenuItem>
          <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
            <Button onClick={user ? onGoogleSignOut : onGoogleSignIn}>
              {user ? "Log Out" : "Log In"}
            </Button>
          </NavigationMenuLink>
        </NavigationMenuItem>
        <NavigationMenuItem>
          {user && <div>{user.name}</div>}
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  );
}
