1) Figure out why boxes are overlapping and why some numbers are appearing directly on top (blocking) the element
- turns out the reason is that there are some generations of no-highlight elements in between two generations of highlighted elements
- unfortunately, we have to choose between allowing elements that are overlapping over independent elements. 
- but is there any way to have both??
- current functionality does not take that into account
1.25) Figure out why text inputs are not tracked but all buttons seem to be tracked
- so it turns out that some text inputs are intentionally marked invisible.
- we might have to resort to NOT highlighting them on the screen, but still keeping track of them separately
- we will need to create a "possibly hidden interactive elements" -> and provide that to the LLM as well. 

1.3)
- Figuring out what qualitifies an element to be highlighted -- more specifically, if its parent isn't in the viewport
- MAYBE, still iterate through entire tree -- but only highlight if in viewport. 
- if parent not in viewport, highlight if no child elements
- or go area based? but that doesn't solve the problem of a parent being out but the child being in...

1.4)
- Shadow nodes aren't working. iframes aren't working

1.5) Figure out how to make the buildDOMTree more efficient. 

4) Figure out how to extract interactive elements which are highlighted into an LLM-comprehensible format 
- did this, although im not sure how comprehensible this is for the LLM.

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
