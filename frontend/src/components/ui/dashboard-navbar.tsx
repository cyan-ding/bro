"use client";

import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu";

import { Button } from "./button";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/useAuthStore";

export function DashboardNavbar() {
  const { user } = useAuthStore();

  const router = useRouter();

  const handleGoogleSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <div className="flex justify-end">
      <NavigationMenu>
        <NavigationMenuList>
          <NavigationMenuItem>
            <NavigationMenuLink
              asChild
              className={navigationMenuTriggerStyle()}
            >
              <Button onClick={handleGoogleSignOut}>Log out</Button>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            {user && <div>{user.name}</div>}
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
    </div>
  );
}
