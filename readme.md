# MicroPython Debugger
This project aims to add Pdb like debug functionality to MicroPython. Thanks to the work of the community by adding in the `sys.settrace()` function that is required to add debug functionality.  This module aims to implement basic debug functionality like `break`, `step`, `next`, `continue` and it is not the intention the implement all the features available in Pdb. 

Besides the basic functionality, this debugger also implements several memory related commands like `mem_free`, `mem_alloc` and `collect`. These are intended to eliminate the use of putting a lot of print statements in the code. 

To prevent a lot of file access and to keep the code small, code itself is not shown on the terminal, instead it shows `BREAK|STOP filename:lineno`

This module is a proof of concept and there is still a lot of improvement possible. 

## Setting Up
Because the `sys.settrace` method adds additional overhead it is not enabled by default in the MicroPython builds. The included `esp32-firmware.bin` has this method enabled. 

**NOTE:** This image is only compatible with ESP32 devices. 

## Commands
Breakpoint  
`b(reak) [ filename:lineno [, condition] ]`  
Without argument, list all breaks. With a file:line number argument, set a break at this line. If a second argument is present, it is a string specifying an expression which must evaluate to true before the breakpoint is honored. 

**NOTE:** Because of optimizations in micropython conditional breakpoints are limited to the global scope. 


Clear  
`cl(ear) filename:lineno`  
`cl(ear) [bpnumber [bpnumber...]]`  
With a space separated list of breakpoint numbers, clear those breakpoints. Without argument, clear all breaks (but first ask confirmation). With a filename:lineno argument, clear all breaks at that line in that file.

Next  
`n(ext)`  
Continue execution until the next line in the current function is reached or it returns.

Step  
``s(tep)``  
Execute the current line, stop at the first possible occasion (either in a function that is called or in the current function).

Until  
`unt(il) [lineno]`  
Without argument, continue execution until the line with a number greater than the current one is reached. With a line number, continue execution until a line with a number greater or equal to that is reached.

Continue  
`c(ont(inue))`  
Continue execution, only stop when a breakpoint is encountered.

P  
`p expression`  
Print the value of the expression.

MemFree  
`mem_free`. `mf`  
Print the available memory  

MemAlloc  
`mem_alloc`, `ma`  
Print the allocated memory  

Collect  
`collect`  
Call the garbage collector  
