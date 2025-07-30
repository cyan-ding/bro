1) Figure out why boxes are overlapping and why some numbers are appearing directly on top (blocking) the element

1.25) Figure out why text inputs are not tracked but all buttons seem to be tracked

1.5) Figure out how to make the buildDOMTree more efficient. 

4) Figure out how to extract interactive elements which are highlighted into an LLM-comprehensible format

5) Figure out how to wrap that, the screenshot, instructions, and history together to feed to the LLM

6) Figure out how to loop that and not have the loop crash immediately.

7) Figure out how to access things beyond the page (tabs, history, passwords) and incorporate that into the existing system. We might have to investigate CDP. 

8) Figure out mechanisms for scrolling. See if there exists a need for it, and what alternatives we have. 

9) Figure out how to use playwright codegen to record a workflow, and reliably repeat it. 

10) Figure out why the metrics aren't accurate 
- bounding rect and client rect hits are always 0
- this might be because we aren't storing the cache anywhere and its getting reset. 
- caches shoudl be written to the browser data. so when the user closes and reopens the browser, the cache remains. 
- performant code is honestly the least priority thing right now. lets focus on creating an mvp
