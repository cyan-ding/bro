1) Read through @highlight.js and write inline comments

2) Figure out how to make the buildDOMTree more efficient. 
- This may entail investigating the utility of having three functions that overlap

3) Figure out how to prevent elements that are stacked on top of each other to not stack

4) Figure out how to extract interactive elements which are highlighted into an LLM-comprehensible format

5) Figure out how to wrap that, the screenshot, instructions, and history together to feed to the LLM

6) Figure out how to loop that and not have the loop crash immediately.

7) Figure out how to access things beyond the page (tabs, history, passwords) and incorporate that into the existing system. We might have to investigate CDP. 

8) Figure out mechanisms for scrolling. See if there exists a need for it, and what alternatives we have. 

9) Figure out how to use playwright codegen to record a workflow, and reliably repeat it. 

