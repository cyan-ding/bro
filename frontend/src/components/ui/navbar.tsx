"use client";

import * as React from "react";
import Link from "next/link";
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
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

function ListItem({
  title,
  children,
  href,
  ...props
}: React.ComponentPropsWithoutRef<"li"> & { href: string }) {
  return (
    <li {...props}>
      <NavigationMenuLink asChild>
        <Link href={href}>
          <div className="text-sm leading-none font-medium">{title}</div>
          <p className="text-muted-foreground line-clamp-2 text-sm leading-snug">
            {children}
          </p>
        </Link>
      </NavigationMenuLink>
    </li>
  );
}
