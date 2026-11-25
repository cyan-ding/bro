"use client"

import { useTheme } from "next-themes"
import { Button } from "./ui/button"
import { Moon, Sun } from "lucide-react"
export function ThemeToggle() {
    const {resolvedTheme, setTheme} = useTheme()

    return (
        <Button
            size="icon"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
            { resolvedTheme === "dark" ? <Sun/> : <Moon/>}
        </Button>
    )
}
