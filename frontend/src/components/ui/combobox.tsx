"use client"

import * as React from "react"
import { Check, ChevronsUpDown } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

interface ComboBoxParams {
    options: Record<string, string>
    display: string
    empty: string
    setter: (value: string) => void
    className?: string
}


export function Combobox(
    {options, display, empty, setter, className }: ComboBoxParams
) {
  const [open, setOpen] = React.useState(false)
  const [displayedValue, setDisplayedValue] = React.useState("")

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn("w-[200px] justify-between", className)}
        >
          {displayedValue
            ? Object.entries(options).find(([key]) => key === displayedValue)?.[0]
            : display}
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className={cn("w-[200px] p-0")}>
        <Command>
          <CommandInput placeholder={display} className="h-9" />
          <CommandList>
            <CommandEmpty>{empty}</CommandEmpty>
            <CommandGroup>
              {Object.entries(options).map(([key, value]) => (
                <CommandItem
                  key={value}
                  value={key}
                  onSelect={() => {
                    setDisplayedValue(key)
                    setter(value)
                    setOpen(false)
                  }}
                >
                  {key}
                  <Check
                    className={cn(
                      "ml-auto",
                      displayedValue === key ? "opacity-100" : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
