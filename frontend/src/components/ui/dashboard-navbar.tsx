"use client";

import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuList,
} from "@/components/ui/navigation-menu";
import { ThemeToggle } from "../ThemeToggle";

export function DashboardNavbar() {
  return (
      <NavigationMenu>
        <NavigationMenuList>
            <NavigationMenuItem>
              <ThemeToggle/>
            </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
  );
}
