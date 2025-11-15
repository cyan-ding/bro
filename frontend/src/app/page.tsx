"use client"
import { useEffect, useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Combobox } from "@/components/ui/combobox"
import { useAgentStore } from "@/store/useAgentStore"



export default function Home() {
    const {
        setModel
    } = useAgentStore();
    const [query, setQuery] = useState("")
    let [models, setModels] = useState({})
    useEffect(() => {
        fetch("/models.json")
            .then((res) => res.json())
            .then((data) => {
                setModels(data)
            });
    }, []
    )


    return (
        <div className="flex justify-center items-center min-h-screen">
            <Textarea
                className="w-1/3"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
            />
            <Combobox
                options={models}
                display={"Select a model"}
                empty={"No model selected"}
                setter={setModel}
            />
        </div>
    )

}