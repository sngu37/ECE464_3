from __future__ import print_function
import os
import copy
import math
import threading
import time
import concurrent.futures
import multiprocessing


# Function List:
# 1. netRead: read the benchmark file and build circuit netlist
# 2. gateCalc: function that will work on the logic of each gate
# 3. [REMOVED] inputRead: function that will update the circuit dictionary made in netRead to hold the line values
# 4. basic_sim: the actual simulation
# 5. main: The main function
# 6. counterGen: takes seed and creates a list s0,s1,s(n+1) till n = 255
# 7. lfsrGen: uses lfsrCalc to simulate a linear lfsr @ 2,3,4 and return an array[0-254]. Last one holds all strins combined
# 8. TVA_gen: Generates an array to be used to create TV_A
# 9. TVB_gen: Generates an array to be used to create TV_B
# 10. TVC_gen: Generates an array to be used to create TV_C
# 11. TVD_gen: Geneartes an array to be used to create TV_D
# 12. TVE_gen: Geneartes an array to be used to create TV_E

# FUNCTION:
def genFaultList(circuit):
    # Creating a list to be returned to the main code
    allFaults = []

    # Go over all the inputs and...
    for x in circuit["INPUTS"][1]:
        # ... write input-SA-0/1 to ...
        toWrite = x[5:] + "-SA-"
        allFaults.append(toWrite + "0")
        allFaults.append(toWrite + "1")

    # Go over all the gates and ...
    for x in circuit["GATES"][1]:
        if x == "wire_scanOut":
            continue
        # ... do the same thing to the gate outputs
        toWrite = x[5:] + "-SA-"
        allFaults.append(toWrite + "0")
        allFaults.append(toWrite + "1")
        
        # ... Also, go over all of the gates' inputs and ...
        for y in circuit[x][1]:
            if y in ["wire_scanIn", "wire_scanEnable", "wire_scanOut"]:
                continue
            # do the same thing except name it OUTPUT-IN-INPUT-SA-0/1
            toWrite0 = x[5:] + "-IN-" + y[5:] + "-SA-"
            allFaults.append(toWrite0 + "0")
            allFaults.append(toWrite0 + "1")
    return allFaults


# FUNCTION:
def readFaults(allFaults, faultFile):
    # Read the the given file
    inFault = open(faultFile, "r")

    # Create list of active faults
    activeFaults = []

    # For each line in the txt file, see if they're part of the available faults
    for x in inFault:
        # Do nothing else if empty lines, ...
        if (x == "\n"):
            continue
        # ... or any comments
        if (x[0] == "#"):
            continue

        # Removing the the newlines at the end and then output it to the txt file
        x = x.replace("\n", "")

        # Removing spaces
        x = x.replace(" ", "")

        flag = False
        for y in allFaults:
            if x == y:
                flag = True
                break
        if flag:
            activeFaults.append([x, False])  # if they are, add them to the list
        else:
            print("ERROR: Fault can not exist in the circuit: " + x)  # Otherwise, tell the user
    return activeFaults


# FUNCTION:
def fault_sim(activeFaults, inputCircuit, goodOutput, nodeLen, batchSize, cycle, initDFF):
    detectedFaults = 0 #[0 for _ in range(0, 25)]

    for x in activeFaults:
        detected = False
        # print("Current fault:", x)
        circuit = copy.deepcopy(inputCircuit)

        xSplit = x.split("-SA-")  # WAS  xSplit = x[0].split("-SA-")

        # Get the value to which the node is stuck at
        value = xSplit[1]
        currentFault = "wire_" + xSplit[0]
        value = value * nodeLen

        if "-IN-" not in currentFault:
            circuit[currentFault][3] = [value] * (cycle+1)
            circuit[currentFault][2] = cycle
            circuit[currentFault][0] = "FAULT"
            if currentFault in circuit["GATES"][1]:
                circuit["GATES"][1].remove(currentFault)
                if currentFault in circuit["DFF"][1]:
                    circuit["DFF"][1].remove(currentFault)
        else:
            currentFault = currentFault.split("-IN-")
            circuit[currentFault[0]][1].remove("wire_" + currentFault[1])
            if circuit[currentFault[0]][0] == "DFF":
                circuit[currentFault[0]][1] = [value] + circuit[currentFault[0]][1]
            else:
                circuit[currentFault[0]][1].append(value)
        
        basic_sim(circuit, nodeLen, cycle, initDFF)
        # goodOutput[i] xor faulty output[i]
        # If xor result >= 1 then fault detected
        # Taking badOutput:
        badOutput = []
        for y in circuit["OUTPUTS"][1]:
            if not circuit[y][2]:
                print("NETLIST ERROR: OUTPUT LINE \"" + y + "\" NOT ACCESSED")
                break
            badOutput += (circuit[y][3])

        for i in range(0,len(goodOutput)):
            goodCurr = int(goodOutput[i],2)
            badCurr = int(badOutput[i],2)
            xorResult = goodCurr ^ badCurr
            if xorResult != 0:
                detected=True
                detectedFaults +=1
                break
            if detected:
                break
        """
        for batch in range(0, 25):
            for increment, y in enumerate(circuit["OUTPUTS"][1]):
                if not circuit[y][2]:
                    print("NETLIST ERROR: OUTPUT LINE \"" + y + "\" NOT ACCESSED")
                    break
                starting_Position = batchSize * (batch)  # try?
                ending_position = batchSize * (batch + 1)
                curr_Good = int(goodOutput[increment][starting_Position:ending_position], 2)
                curr_Fault = int(circuit[y][3][starting_Position:ending_position], 2)
                starting_Position
                XORed = curr_Fault ^ curr_Good
                if XORed != 0:
                    detected = True
                    for temp in range(batch, 25):
                        detectedFaults[temp] += 1
                    break
            if detected:
                break
        """
    return detectedFaults

# -------------------------------------------------------------------------------------------------------------------- #
#FUNCTION: Allows all functions to access the start 
def cycTag():
    return -1
# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: Neatly prints the Circuit Dictionary:
def printCkt(circuit):
    print("INPUT LIST:")
    for x in circuit["INPUTS"][1]:
        print(x + "= ", end='')
        print(circuit[x])

    print("\nOUTPUT LIST:")
    for x in circuit["OUTPUTS"][1]:
        print(x + "= ", end='')
        print(circuit[x])

    print("\nGATE list:")
    for x in circuit["GATES"][1]:
        print(x + "= ", end='')
        print(circuit[x])
    print()


# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: Reading in the Circuit gate-level netlist file:
def netRead(netName, initDFF):
    # Opening the netlist file:
    netFile = open(netName, "r")

    # temporary variables
    inputs = []  # array of the input wires
    outputs = []  # array of the output wires
    gates = []  # array of the gate list
    inputBits = 0  # the number of inputs needed in this given circuit
    DFF_list = [] # Temporary DFF list


    # main variable to hold the circuit netlist, this is a dictionary in Python, where:
    # key = wire name; value = a list of attributes of the wire
    circuit = {}

    # Fast processing
    completed_queue = []
    leftovers_queue = []

    # Reading in the netlist file line by line
    for line in netFile:

        # NOT Reading any empty lines
        if (line == "\n"):
            continue

        # Removing spaces and newlines
        line = line.replace(" ", "")
        line = line.replace("\n", "")
        line = line.upper()

        # NOT Reading any comments
        if (line[0] == "#"):
            continue

        # @ Here it should just be in one of these formats:
        # INPUT(x)
        # OUTPUT(y)
        # z=LOGIC(a,b,c,...)

        # Read a INPUT wire and add to circuit:
        if (line[0:5] == "INPUT"):
            # Removing everything but the line variable name
            line = line.replace("INPUT", "")
            line = line.replace("(", "")
            line = line.replace(")", "")

            # Format the variable name to wire_*VAR_NAME*
            line = "wire_" + line

            # Error detection: line being made already exists
            if line in circuit:
                msg = "NETLIST ERROR: INPUT LINE \"" + line + "\" ALREADY EXISTS PREVIOUSLY IN NETLIST"
                print(msg + "\n")
                return msg

            completed_queue.append(line)

            # Appending to the inputs array and update the inputBits
            inputs.append(line)

            # add this wire as an entry to the circuit dictionary
            circuit[line] = ["INPUT", line, cycTag(), ['']]

            inputBits += 1
            print(line)
            print(circuit[line])
            continue

        # Read an OUTPUT wire and add to the output array list
        # Note that the same wire should also appear somewhere else as a GATE output
        if line[0:6] == "OUTPUT":
            # Removing everything but the numbers
            line = line.replace("OUTPUT", "")
            line = line.replace("(", "")
            line = line.replace(")", "")

            # Appending to the output array
            outputs.append("wire_" + line)
            continue

        # Read a gate output wire, and add to the circuit dictionary
        lineSpliced = line.split("=")  # splicing the line at the equals sign to get the gate output wire
        gateOut = "wire_" + lineSpliced[0]

        # Error detection: line being made already exists
        if gateOut in circuit:
            msg = "NETLIST ERROR: GATE OUTPUT LINE \"" + gateOut + "\" ALREADY EXISTS PREVIOUSLY IN NETLIST"
            print(msg + "\n")
            return msg

        lineSpliced = lineSpliced[1].split("(")  # splicing the line again at the "("  to get the gate logic
        logic = lineSpliced[0].upper()
        

        lineSpliced[1] = lineSpliced[1].replace(")", "")
        terms = lineSpliced[1].split(",")  # Splicing the the line again at each comma to the get the gate terminals
        # Turning each term into an integer before putting it into the circuit dictionary
        terms = ["wire_" + x for x in terms]   
            
        # add the gate output wire to the circuit dictionary with the dest as the key
        circuit[gateOut] = [logic, terms, cycTag(), ['']]
        # TEMP. FIX
        gates.append(gateOut)
        if logic == "DFF":
            if len(DFF_list) == 0:
                terms.append("wire_scanIn")
                DFF_list.append(gateOut)
            else:
                DFF_list.append(gateOut)
                terms.append(DFF_list[-1])
            terms.append("wire_scanEnable")
            if initDFF == 0:
                circuit[gateOut][3] = ['1']
            elif initDFF == 1:
                circuit[gateOut][3] = ['0']
            elif initDFF == 2:
                circuit[gateOut][3] = ['U']    
        """
        # following check if all terms have been discovered
        temp_to_check_terms_available = len(terms)
        for t in terms:
            if t in completed_queue:
                temp_to_check_terms_available -= 1

        if temp_to_check_terms_available == 0:  # if 0 all terms have been discovered already
            # Appending the dest name to the gate list
            gates.append(gateOut)
            completed_queue.append(gateOut)
        else:
            leftovers_queue.append(gateOut)

    # Finish up the ordering
    while len(leftovers_queue):
        print ("leftovers_queue: \n")
        print (leftovers_queue)
        print ("\n\n\n\ncompleted_queue: \n")
        print (completed_queue)
        currgate = leftovers_queue[0]
        terms = circuit[currgate][1]
        temp_to_check_terms_available = len(terms)
        for t in terms:
            if t in completed_queue:
                temp_to_check_terms_available -= 1
        if temp_to_check_terms_available == 0:
            gates.append(currgate)
            completed_queue.append(currgate)
            del leftovers_queue[0]
        else:
            leftovers_queue.append(currgate)
            del leftovers_queue[0]
        """
    # now after each wire is built into the circuit dictionary,
    # add a few more non-wire items: input width, input array, output array, gate list
    # for convenience
    gates.append("wire_scanOut") #adds scanOut wire to circuit

    #Creating ScanIn and ScanOut
    circuit["wire_scanIn"] = ["scanIn", "n/a", cycTag(), ['']]
    circuit["wire_scanEnable"] = ["scanEnable", "n/a", cycTag(), ['']]
    circuit["wire_scanOut"] = ["scanOut", [DFF_list[-1], "wire_scanIn", 'wire_scanEnable'], cycTag(), ['']]

    circuit["INPUT_WIDTH"] = ["input width:", inputBits]
    circuit["INPUTS"] = ["Input list", inputs]
    circuit["OUTPUTS"] = ["Output list", outputs]
    circuit["GATES"] = ["Gate list", gates]
    circuit["DFF"] = ["DFF list", DFF_list]

    print("\n bookkeeping items in circuit: \n")
    print(circuit["INPUT_WIDTH"])
    print(circuit["INPUTS"])
    print(circuit["OUTPUTS"])
    print(circuit["GATES"])

    return circuit

# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: calculates the output value for each logic gate (UNINITIALIZED)
def uninitGateCalc(circuit, node, nodeLen, cycle):
    terminals = []
    # terminal will contain all the input wires of this logic gate (node)
    for gate in list(circuit[node][1]):
        if gate in ['0' * nodeLen, '1' * nodeLen, 'U' * nodeLen]:
            terminals.append(gate)
        else:
            # print(circuit[gate][3])
            gate = circuit[gate][3]
            terminals.append(gate)

    # Make a variable that will list all the Test Vectors
    # terminals = "147", "257", "369"
    # toTest = "123", "456", "789"
    toTest = list(zip(*terminals))

     # If the node is a buffer gate output, solve and return the output
    if circuit[node][0] == "BUFF":
        circuit[node][3][cycle] = terminals[0][cycle]
        return circuit
    
    elif circuit[node][0] == "FAULT":
        circuit[node][3][cycle] = circuit[node][3][0]

    # Initialize the output
    circuit[node][3][cycle] = ''

    for eachNode in toTest:
        # If the node is an Inverter gate output, solve and return the output
        if circuit[node][0][cycle] == "NOT":
            if eachNode[0] == '0':
                circuit[node][3][cycle] += '1'
            elif eachNode[0] == '1':
                circuit[node][3][cycle] += '0'
            elif eachNode[0] == "U":
                circuit[node][3][cycle] += "U"
            else:  # Should not be able to come here
                return -1
            return circuit
        
        # If the node is a DFF gate output, solve and return the output
        elif circuit[node][0] == "DFF":
            if len(circuit[node][3]) >= cycle:
                print("ERROR: Current cycle should not be accessed")
            circuit[node][3][cycle] += eachNode[eachNode[2]]
            return circuit 

        # If the node is an AND gate output, solve and return the output
        elif circuit[node][0] == "AND":
            # Initialize the output to 1
            toOutput = '1'
            # Initialize also a flag that detects a U to false
            unknownTerm = False  # This will become True if at least one unknown terminal is found
            # if there is a 0 at any input terminal, AND output is 0. If there is an unknown terminal, mark the flag
            # Otherwise, keep it at 1
            for thisNode in eachNode:  
                if thisNode == '0':
                    toOutput = '0'
                    break
                if thisNode == "U":
                    unknownTerm = True
            if unknownTerm:
                if toOutput == '1':
                    toOutput= "U"
            circuit[node][3][cycle] += toOutput
            return circuit

        # If the node is a NAND gate output, solve and return the output
        elif circuit[node][0] == "NAND":
            # Initialize the output to 0
            toOutput = '0'
            # Initialize also a flag that detects a U to false
            unknownTerm = False  # This will become True if at least one unknown terminal is found
            # if there is a 0 at any input terminal, AND output is 0. If there is an unknown terminal, mark the flag
            # Otherwise, keep it at 0
            for thisNode in eachNode:  
                if thisNode == '0':
                    toOutput = '1'
                    break
                if thisNode == "U":
                    unknownTerm = True
            if unknownTerm:
                if toOutput == '0':
                    toOutput = "U"
            circuit[node][3][cycle] += toOutput
            return circuit

        # If the node is an OR gate output, solve and return the output
        elif circuit[node][0] == "OR":
            # Initialize the output to 0
            toOutput = '0'
            # Initialize also a variable that detects a U to false
            unknownTerm = False  # This will become True if at least one unknown terminal is found

            # if there is a 1 terminal, OR changes the output to 1. Otherwise, keep it at 0
            for thisNode in eachNode: 
                if thisNode == '1':
                    toOutput = '1'
                    break
                if toOutput == "U":
                    unknownTerm = True

            if unknownTerm:
                if toOutput == '0':
                    toOutput = "U"
            circuit[node][3][cycle] += toOutput
            return circuit

        # If the node is an NOR gate output, solve and return the output
        elif circuit[node][0] == "NOR":
            # Initialize the output to 0
            toOutput = '1'
            # Initialize also a variable that detects a U to false
            unknownTerm = False  # This will become True if at least one unknown terminal is found

            # if there is a 1 terminal, OR changes the output to 1. Otherwise, keep it at 0
            for thisNode in eachNode: 
                if thisNode == '1':
                    toOutput = '0'
                    break
                if toOutput == "U":
                    unknownTerm = True

            if unknownTerm:
                if toOutput == '1':
                    toOutput = "U"
            circuit[node][3][cycle] += toOutput
            return circuit

        # If the node is an XOR gate output, solve and return the output
        elif circuit[node][0] == "XOR":
            # Initialize a variable to zero, to count how many 1's in the terms
            count = 0

            # if there are an odd number of terminals, XOR outputs 1. Otherwise, it should output 0
            for thisNode in eachNode:
                if thisNode == '1':
                    count += 1  # For each 1 bit, add one count
                if thisNode == "U":
                    circuit[node][3][cycle] += "U"
                    return circuit

            # check how many 1's we counted
            if count % 2 == 1:  # if more than one 1, we know it's going to be 0.
                circuit[node][3][cycle] +=  '1'
            else:  # Otherwise, the output is equal to how many 1's there are
                circuit[node][3][cycle] +=  '0'
            return circuit

        # If the node is an XNOR gate output, solve and return the output
        elif circuit[node][0] == "XNOR":
            # Initialize a variable to zero, to count how many 1's in the terms
            count = 0

            # if there are an odd number of terminals, XOR outputs 1. Otherwise, it should output 0
            for thisNode in eachNode:
                if thisNode == '1':
                    count += 1  # For each 1 bit, add one count
                if thisNode == "U":
                    circuit[node][3][cycle] += "U"
                    return circuit

            # check how many 1's we counted
            if count % 2 == 1:  # if more than one 1, we know it's going to be 0.
                circuit[node][3][cycle] +=  '0'
            else:  # Otherwise, the output is equal to how many 1's there are
                circuit[node][3][cycle] +=  '1'
            return circuit


    # Error detection... should not be able to get at this point
    return circuit[node][0]

# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: calculates the output value for each logic gate (INITIALIZED)
def gateCalc(circuit, node, nodeLen, cycle):
    terminals = []
    # terminal will contain all the input wires of this logic gate (node)
    for gate in list(circuit[node][1]):
        if circuit[node][0] in ["DFF", "scanOut"]:
            terminals.append(gate)
        elif gate in ['0' * nodeLen, '1' * nodeLen, 'U' * nodeLen]:
            if(gate == 'U' * nodeLen):
                print("ERROR: UNKNOWN found in " + node + " for initialized gateCalc.")
                exit()
            gate = int("0" + gate, 2)  # Turning the gate into an int and appending it to the terminals
            terminals.append(gate)
        else:
            # print(circuit[gate][3])
            gate = int(("0" + circuit[gate][3][cycle]), 2)
            terminals.append(gate)
    
    # If the node is an Inverter gate output, solve and return the output
    if circuit[node][0] == "NOT":
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format((2 ** nodeLen) + (~terminals[0]))
        return circuit

    # If the node is a buffer gate output, solve and return the output
    elif circuit[node][0] == "BUFF":
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format(terminals[0])
        return circuit
    # If the node is a DFF gate output, solve and return the output
    elif circuit[node][0] == "DFF":
        if circuit[node][2] > cycle:
            print("ERROR: Current cycle should not be accessed")

        #print(terminals[int(circuit[terminals[2]][3][0][cycle])])
        place = terminals[int(circuit[terminals[2]][3][0][cycle])]
        if place in ['0'*nodeLen,'1'*nodeLen]:
            circuit[node][3][cycle] = place
        else:
            circuit[node][3][cycle] = circuit[place][3][cycle-1]

        """
        # Scan Chain
        # We want to check position of DFF
        # Acts as a MUX gate; checking scanEnable and scanIn 
        DFFlist = circuit["DFF"][1]    # Pulls DFF list
        scanEnCheck = circuit["wire_scanEnable"][3][0] # Pulls scanEnable values
        scanningIn = circuit["wire_scanIn"][3][0]  # Pulls scanIn values
        if circuit[node][0] == DFFlist[0]:
            #Checking if it's the first DFF
            if scanEnCheck[cycle] == 1: #.append(scanningIn[cycle])
                circuit[node][3][cycle]=scanningIn[cycle]
        elif circuit[node][0] != DFFlist[0]:
            #changing scanningIn value to be the older value of the previous DFF
            if scanEnCheck[cycle] == 1:
                circuit[node][3]=circuit[node][1][1][cycle-1]
        """
        return circuit 
        
    # IF the node is the ScanOut wire, pull the value from last DFF in scan chain
    elif circuit[node][0] == "scanOut":
        lastDFF = circuit["DFF"][1][-1]  # Calls the last DFF in DFF list
        lastDFF = circuit[lastDFF][3] # Calls the values held by that DFF 
        scanOutVal = lastDFF[cycle-1] # Calls the previous cycles value
        circuit["wire_scanOut"][3][cycle] = scanOutVal
        return circuit
    # If the node is an AND gate output, solve and return the output
    elif circuit[node][0] == "AND":
        output = int("0" + ("1" * nodeLen), 2)
        for term in terminals:
            output = output & term
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format(output)
        return circuit

    # If the node is a NAND gate output, solve and return the output
    elif circuit[node][0] == "NAND":
        output = int("0" + ("1" * nodeLen), 2)
        for term in terminals:
            output = output & term
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format((2 ** nodeLen) + (~output))
        return circuit

    # If the node is an OR gate output, solve and return the output
    elif circuit[node][0] == "OR":
        output = int("0" + ("0" * nodeLen), 2)
        for term in terminals:
            output = output | term
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format(output)
        return circuit

    # If the node is an NOR gate output, solve and return the output
    elif circuit[node][0] == "NOR":
        output = int("0" + ("0" * nodeLen), 2)
        for term in terminals:
            output = output | term
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format((2 ** nodeLen) + (~output))
        return circuit

    # If the node is an XOR gate output, solve and return the output
    elif circuit[node][0] == "XOR":
        output = int("0" + ("0" * nodeLen), 2)
        for term in terminals:
            output = output ^ term
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format(output)
        return circuit

    # If the node is an XNOR gate output, solve and return the output
    elif circuit[node][0] == "XNOR":
        output = int("0" + ("0" * nodeLen), 2)
        for term in terminals:
            output = output ^ term
        circuit[node][3][cycle] = ("{0:0" + str(nodeLen) + "b}").format((2 ** nodeLen) + (~output))
        return circuit

    elif circuit[node][0] == "FAULT":
        circuit[node][3][cycle] = circuit[node][3][0]

    # Error detection... should not be able to get at this point
    return circuit[node][0]


# LFSR helper
def linearCalc(initalVal):
    temp = initalVal[0]  # Get the MSB
    sBinary = initalVal[-7:]

    xorVals = int(sBinary[3:6]) ^ int(temp + temp + temp)
    sBinary = sBinary[0:3] + repr(xorVals).zfill(3) + sBinary[6:7] + temp  # final value
    return sBinary


# Basic counter for TV A ~ C
def counterGen(seed):
    counterBin = []
    initialVal = int(seed)
    for _ in range(0, 255):
        counterBin.append(initialVal)
        initialVal += 1
        if initialVal > 255:
            initialVal=0
    return counterBin


# LFSR looper
def lfsrGen(seed):
    lfsrSeq, lfsrSeqBin = "", []
    initalVal = bin(seed)[2:].zfill(8)
    lfsrSeq = initalVal + lfsrSeq
    lfsrSeqBin.append(initalVal)

    currentVal = linearCalc(initalVal)
    while initalVal != currentVal:
        lfsrSeq = currentVal + lfsrSeq  # save
        lfsrSeqBin.append(currentVal)
        currentVal = linearCalc(currentVal)

    lfsrSeqBin.append(lfsrSeq)
    return lfsrSeqBin


# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: Updating the circuit dictionary with the TV batches, and also resetting the gates and output lines
# NEEDED:
#   • circuit == circuit dictionary
#   • TVbatch == Current batch number of TV_user_array
#   • fault_list == the active fault_list
def TVSim(circuit, TVbatch, fault_list, batchSize, cycle, initDFF):
    holdthecircuit = copy.deepcopy(circuit)
    # Counting increment on how many Input sets we are passing thru
    TVcount = 0

    # For every TV, we update our inputs
    for line in TVbatch:

        # TV count increments up
        TVcount += 1

        # Checking if input bits are enough for the circuit
        if len(line) < holdthecircuit["INPUT_WIDTH"][1]:
            return -1

        # Getting the proper number of bits:
        line = line[(len(line) - holdthecircuit["INPUT_WIDTH"][1]):(len(line))]

        # Adding the inputs to the dictionary
        # Since the for loop will start at the most significant bit, we start at input width N
        i = holdthecircuit["INPUT_WIDTH"][1] - 1
        inputs = list(holdthecircuit["INPUTS"][1])

        # dictionary item: [(bool) If accessed, (int) the value of each line, (int) layer number, (str) origin of U value]
        # line: string
        for bitVal in line:
            # bitVal = bitVal.upper()  # in the case user input lower-case u
            holdthecircuit[inputs[i]][3][0] += bitVal  # put the bit value as the line value ##WAS circuit[inputs[i]][3].append(bitVal)
            holdthecircuit[inputs[i]][2] = 0  # and make it so that this line is accessed if it hasn't already

            # In case the input has an invalid character (i.e. not "0", "1" or "U"), return an error flag
            if bitVal != "0" and bitVal != "1":
                return -2
            i -= 1  # continuing the increments
    for i in list(holdthecircuit["INPUTS"][1]):
        holdthecircuit[i][3] = [holdthecircuit[i][3][0]] * len(holdthecircuit[i][3])
        holdthecircuit[i][2] = cycle
    # Creating a deepcopy to be used to easily reset the circuit with the current TV's
    circReset = copy.deepcopy(holdthecircuit)

    # Inputs should have len(TVlist)-bits first TV from the left to right
    basic_sim(holdthecircuit, TVcount, cycle, initDFF)

    # print("...Done\n\nCreating goodOutput...")
    # Get the goodOutput
    goodOutput = []
    for y in holdthecircuit["OUTPUTS"][1]:
        if not holdthecircuit[y][2]:
            print("NETLIST ERROR: OUTPUT LINE \"" + y + "\" NOT ACCESSED")
            break
        goodOutput += (holdthecircuit[y][3])
    # print("...done\n")
    # print("Simulating bad circuits...")
    return fault_sim(fault_list, circReset, goodOutput, TVcount, batchSize, cycle, initDFF)


# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: the actual simulation #
def basic_sim(circuit, nodeLen, numCycle, initDFF):
    # Creating a queue, using a list, containing all of the gates in the circuit
    queue = list(circuit["GATES"][1])
    currCycle = 0 # currCycle is the current cycle; numCycle is the cycles inputted by the user
    # i would be the decrementing variable that will be tell the loop when to increment currCycle
    i = len(queue) - len(circuit["DFF"][1]) - 1

    while currCycle <= numCycle:
        # If there's no more things in queue, done
        if i == 0:
            i = len(queue)
            currCycle += 1
            continue

        # Remove the first element of the queue and assign it to a variable for us to use
        curr = queue[0]
        queue.remove(curr)

        # If the current gate is in or has finished the current cycle, we skip it
        if circuit[curr][2] >= currCycle:
            queue.append(curr)
            continue

        # initialize a flag, used to check if every terminal has been accessed
        term_has_value = True

        # Check if the terminals have been accessed
        for term in circuit[curr][1]:
            # If the terminal is a constant value, term is fine
            if term in ["0" * (nodeLen), "1" * nodeLen, "U" * nodeLen]:  # ['1', '0', 'U']:
                continue
            # Formerly, """"elif not circuit[term][2]:""""
            # If the terminal has not been accessed in the cycle, update term_has_value flag
            elif circuit[curr][0] == "DFF" and currCycle > 0 and circuit[term][2] >= (currCycle-1):
                continue
            elif  circuit[term][2] < currCycle:
                term_has_value = False
                break

        # If terminals are good to go, ...
        if term_has_value:
            circuit[curr][2] = currCycle
            if initDFF == "2":
                circuit = uninitGateCalc(circuit, curr, nodeLen, currCycle)
            else:
                circuit = gateCalc(circuit, curr, nodeLen, currCycle)

            # ERROR Detection if LOGIC does not exist
            if isinstance(circuit, str):
                print("LOGIC NOT DETECTED: " + circuit)
                return circuit
            
            queue.append(curr)
            i -= 1

            # print("Progress: updating " + curr + " = " + circuit[curr][3] + " as the output of " + circuit[curr][0] + " for:")
            # for term in circuit[curr][1]:
            #    if term in ['1','0','U']:
            #        print(term + " = "+ term)
            #    else:
            #        print(term + " = " + circuit[term][3])
            #
            # print("\nPress Enter to Continue...")
            # input()

        else:
            # If the terminals have not been accessed yet, append the current node at the end of the queue
            queue.append(curr)

    return circuit


# one N-Bit counter [0,0,0,0,80] in binary fills bits 0 ~ 24 with 0s
# returns list for TV_A generation
def TVA_gen(counterBin, inputSize):
    TVA_list = []
    for x in range(0, 255):
        currVal = counterBin[x]
        binVal = bin(currVal)[2:].zfill(inputSize)
        finalVal = str(binVal)
        finalVal = finalVal[-1 * inputSize:]
        TVA_list.append(finalVal)
    return TVA_list


# multi 8-bit counter [80,80,80,80,80] in binary
# returns list for TV_B generation
def TVB_gen(counterBin, inputSize):
    TVB_list = []
    for x in range(0, 255):
        currVal = counterBin[x]
        binVal = bin(currVal)[2:].zfill(8)
        iteration = inputSize // 8 + 1
        finalVal = str(binVal) * iteration
        finalVal = finalVal[-1 * inputSize:]
        TVB_list.append(finalVal)
    return TVB_list


# +1 counter multi 8-bit "diff seed" [84,83,82,81,80], [85,84,83,82,81], etc in binary
# returns list for TV_C generation
def TVC_gen(counterBin, inputSize):
    TVC_list = []
    for x in range(0, 255):
        tempBin = ""
        currVal = counterBin[x]
        iteration = inputSize // 8 + 1
        for _ in range(0, iteration):
            tempVal = str(bin(currVal)[2:].zfill(8))
            tempBin = tempVal + tempBin
            currVal += 1
        TVC_list.append(tempBin[-1 * inputSize:])
    return TVC_list


# takes inputsize of the circuit, And the global variable that hold LFSR sequence
# returns list for TV_D geneartion
def TVD_gen(lfsrSeqBin, inSize):
    TVD_list = []
    for x in range(0, 255):
        inputSize = inSize
        currVal = lfsrSeqBin[x]  # curr s0->s1->s2
        leftoverSize = inputSize % 8
        inputSize = int((inputSize - leftoverSize) / 8)
        TVD_list.append(currVal[-1 * leftoverSize:] + (currVal * inputSize))
    return TVD_list


# takes inputsize of the circuit, And the global variable that hold LFSR sequence
# returns list for TV_E geneartion
def TVE_gen(lfsrSeq, inputSize):
    lfsrSeq = lfsrSeq[-1]
    TVE_list = []
    start, end = len(lfsrSeq) - inputSize, len(lfsrSeq)
    for _ in range(0, 255):
        if (start < 0):
            start = 2040 + start
        if (end < 0):
            end = 2040 + end
        if (start < end):
            TVE_list.append(lfsrSeq[start:end])
        elif (start > end):
            TVE_list.append(lfsrSeq[start:] + lfsrSeq[0:end])
        start -= 8
        end -= 8
    return TVE_list


# used to read in user's TV and put into a big array
def importTVs(TV_Stream):
    anArray = []
    for i, line in enumerate(TV_Stream):
        line = line.replace("\n", "")
        if line[0] == "#":
            continue
        anArray.append(line)
        if (i + 1) == 255:
            TV_Stream.close()
            return anArray

    # should not reach this point
    TV_Stream.close()
    print("Not Enough TV's\nBad Input file\n")
    return 0


def extreme_simulator_helper(A, B, C, D, E, circuit, batchSize, full_faults, cycle, initDFF):  # B,C,D,E,

    tempA = TVSim(circuit, A, full_faults, batchSize, cycle, initDFF)
    tempB = TVSim(circuit, B, full_faults, batchSize, cycle, initDFF)
    tempC = TVSim(circuit, C, full_faults, batchSize, cycle, initDFF)
    tempD = TVSim(circuit, D, full_faults, batchSize, cycle, initDFF)
    tempE = TVSim(circuit, E, full_faults, batchSize, cycle, initDFF)
    print("Done with a seed")
    return tempA, tempB, tempC, tempD, tempE


# -------------------------------------------------------------------------------------------------------------------- #
# FUNCTION: Main Function
def main():
    # **************************************************************************************************************** #
    # NOTE: UI code; Does not contain anything about the actual simulation
    pattern = ["10","00","11"]
    # Used for file access
    script_dir = os.path.dirname(__file__)  # <-- absolute dir the script is in
    initDFF = -1
    genSeedOnly = False
    cktSimulation = False
    extraCredit = False
    print("Sequential Circuit Simulator:")
    cktSimulation = True
    while True:
        print("\n Select how to initialize the DFFs:")
        print(" (1) Initialize DFFs to 1")
        print(" (2) Initialize DFFs to 0")
        #print(" (3) Scan in... (goto scan selection menu)")
        userInput = input("\n Select from 1-2: ")
        if userInput == "1":
            initDFF = 0
            break
        elif userInput == "2":
            initDFF = 1
            break
        #elif userInput == "3":
        #    initDFF = 2
        #    break
    
    scanInPattern = -1
    while initDFF == 2:
        print("\n Select what to scan in:")
        print(" (1) Scan in: 1010...")
        print(" (2) Scan in: 0000...")
        print(" (3) Scan in: 1111...")
        userInput = input("\n Select from 1-3: ")
        if userInput in ["1","2","3"]:
            scanInPattern = int(userInput) - 1
            break

    # Asks for # of cycles the user wants to run for
    while True:
        print("\n How many cycles do you want to run this circuit? (1 to 100) \n")
        inputCycle = int(input())
        if inputCycle < 1 or inputCycle > 100:
            print("Please select a number from 1 to 100")
            continue
        break

    # Select circuit benchmark file, default is circuit.bench
    while True:
        cktFile = "circuit.bench"
        print("\n Read circuit benchmark file: use " + cktFile + "?" + " Enter to accept or type filename: ")
        userInput = input()
        if userInput == "":
            cktFile = os.path.join(script_dir, cktFile)
            break
        else:
            cktFile = os.path.join(script_dir, userInput)
            if not os.path.isfile(cktFile):
                print("File does not exist. \n")
            else:
                break

    print("\n Reading " + cktFile + " ... \n")
    circuit = netRead(cktFile, initDFF)
    print("\n Finished processing benchmark file and built netlist dictionary: \n")
    # printCkt(circuit)
    l = 0

    # Updating values: [PROJECT 3 NEEDED]
    for z in circuit:
        if z in ["INPUT_WIDTH", "INPUTS", "OUTPUTS", "GATES", "DFF"]:
            continue
        circuit[z][3] = [""] * (inputCycle+1)
        if z not in ["wire_scanEnable", "wire_scanIn", "wire_scanOut"]:
            if circuit[z][0] == "DFF":
                if initDFF == 0:
                    circuit[z][3][0] = '1'
                elif initDFF == 1:
                    circuit[z][3][0] = '0'
                elif initDFF == 2:
                    circuit[z][3][0] = '0'
                circuit[z][2] = 0
        elif z == "wire_scanEnable":
            circuit[z][2] = inputCycle
            # Number of Cycles
            cycles2Run = (inputCycle+1)# - numOfScans ---REMOVED DUE TO DUY's OBJECTION 
            if initDFF != 2:
                circuit[z][3][0] = "0"*cycles2Run

            while cycles2Run > 0:
                # Number of DFFs
                numOfScans = len(circuit["DFF"][1])
                while numOfScans > 0 and cycles2Run > 0:
                    # SCANNING IN THINGS FIRST:
                    circuit[z][3][0] += "1"
                    numOfScans -= 1
                    cycles2Run -= 1
                # DON'T SCAN when circuit is "combinational"
                circuit[z][3][0] += "0"
                cycles2Run -= 1
            
            # SCAN OUT (REMOVED DUE TO STEVEN's OBJECTION)
            # circuit[z][3] += "1"
        
        elif z == "wire_scanIn":
            circuit[z][2] = inputCycle
            # Number of Cycles
            cycles2Run = (inputCycle+1) # - numOfScans ---REMOVED DUE TO DUY's OBJECTION 
            while cycles2Run > 0:
                # Number of DFFs
                numOfScans = len(circuit["DFF"][1])+1
                while numOfScans > 0 and cycles2Run > 0:
                    # SCANNING IN THINGS FIRST:
                    circuit[z][3][0] += pattern[scanInPattern][l]
                    numOfScans -= 1
                    cycles2Run -= 1
                    if l == 0:
                        l = 1
                    else:
                        l = 0
                # DON'T SCAN when circuit is "combinational"
                circuit[z][3][0] += "1" # ARBITRARY NUMBER
                cycles2Run -= 1
            
            # SCAN OUT (REMOVED DUE TO STEVEN's OBJECTION)
            # circuit[z][3] += "1"
        elif z == "wire_scanOut":
            circuit[z][2] = 0
            circuit[z][3][0] = 'U'
            
    """
    # project 2
    if genSeedOnly:
        while True:
            seed = input("What is your seed value in integer: ")
            if seed.isdigit():
                seed = int(seed)
                if ((seed <= 255) and (seed > 0)):
                    break
    if cktSimulation or extraCredit:
        while True:
            batchSize = input("Choose a batch size in [1, 10]: ")
            if batchSize.isdigit():
                batchSize = int(batchSize)
                if ((batchSize <= 10) and (batchSize >= 1)):
                    break
    """
    batchSize = 10 # Not really needed
    # Create TV files here
    if genSeedOnly:
        counterBin = counterGen(seed)
        lfsrSeqBin = lfsrGen(seed)  # creates lfsr based on the seed
        inputSize = circuit["INPUT_WIDTH"][1]  # hold the number of inputs

        TVA_Output = open(os.path.join(script_dir, "TV_A.txt"), "w")
        for a in TVA_gen(counterBin, inputSize):
            TVA_Output.write(a + "\n")
            # TVA_Output.write(hex(int(a, 2)) + "\n")
        TVA_Output.close()

        TVB_Output = open(os.path.join(script_dir, "TV_B.txt"), "w")
        for b in TVB_gen(counterBin, inputSize):
            TVB_Output.write(b + "\n")
            # TVB_Output.write(hex(int(b, 2)) + "\n")
        TVB_Output.close()

        TVC_Output = open(os.path.join(script_dir, "TV_C.txt"), "w")
        for c in TVC_gen(counterBin, inputSize):
            TVC_Output.write(c + "\n")
            # TVC_Output.write(hex(int(c, 2)) + "\n")
        TVC_Output.close()

        TVD_Output = open(os.path.join(script_dir, "TV_D.txt"), "w")
        for d in TVD_gen(lfsrSeqBin, inputSize):
            TVD_Output.write(d + "\n")
            # TVD_Output.write(hex(int(d, 2)) + "\n")
        TVD_Output.close()

        TVE_Output = open(os.path.join(script_dir, "TV_E.txt"), "w")
        for e in TVE_gen(lfsrSeqBin, inputSize):
            TVE_Output.write(e + "\n")
            # TVE_Output.write(hex(int(e, 2)) + "\n")
        TVE_Output.close()
        print("TV's A - E processed with seed: " + str(seed))

    # Make header for the csv file
    # NEED TO make a hook to find i can make this file
    if cktSimulation:
        csvFile = open(os.path.join(script_dir, "f_cvg.csv"), "w")
        getSeed = open(os.path.join(script_dir, "TV_A.txt"), "r")
        seed = getSeed.readline()
        seed = seed.replace("\n", "")
        seed = int(seed[-8:], 2)
        csvFile.write("Batch #, A, B, C, D, E, seed = " + str(seed) + ", Batch size = " + repr(batchSize) + "\n")

    if cktSimulation or extraCredit:
        while True:
            userInput = input("Press enter to use all the faults, else type in the name of the fault file:\n")
            if userInput == "":
                full_faults = genFaultList(circuit)
                print("Processing\n")
                break
            else:
                faultFile = os.path.join(script_dir, userInput)
                if not os.path.isfile(cktFile):
                    print("File does not exist. \n")
                else:
                    full_faults = readFaults(genFaultList(circuit), faultFile)
                    print("Processing\n")
                    break

            if len(full_faults) < 1:
                print("ERROR: No compatible faults found in f_list.txt")
                exit()

    # Note: UI code;
    # **************************************************************************************************************** #

    if cktSimulation:
        total_fault_size = len(full_faults)

        t1 = time.perf_counter()

        tempA = TVSim(circuit, importTVs(open(os.path.join(script_dir, "TV_A.txt"), "r")), full_faults, batchSize,inputCycle, initDFF)
        tempB = TVSim(circuit, importTVs(open(os.path.join(script_dir, "TV_B.txt"), "r")), full_faults, batchSize,inputCycle, initDFF)
        tempC = TVSim(circuit, importTVs(open(os.path.join(script_dir, "TV_C.txt"), "r")), full_faults, batchSize,inputCycle, initDFF)
        tempD = TVSim(circuit, importTVs(open(os.path.join(script_dir, "TV_D.txt"), "r")), full_faults, batchSize,inputCycle, initDFF)
        tempE = TVSim(circuit, importTVs(open(os.path.join(script_dir, "TV_E.txt"), "r")), full_faults, batchSize,inputCycle, initDFF)

        print(tempA)
        print(tempB)
        print(tempC)
        print(tempD)
        print(tempE)
       
        csvFile.write(str(1) + ", " + str(round((tempA / total_fault_size) * 100, 2)) + ", " + str(
            round((tempB / total_fault_size) * 100, 2))
                        + ", " + str(round((tempC / total_fault_size) * 100, 2)) + ", " + str(
            round((tempD / total_fault_size) * 100, 2)) + ", " +
                        str(round((tempE / total_fault_size) * 100, 2)) + "\n")

        print("Time: " + str(time.perf_counter() - t1))
        csvFile.close()

    ###############################################################

    if extraCredit:
        t1 = time.perf_counter()
        inputSize = circuit["INPUT_WIDTH"][1]  # hold the number of inputs
        total_fault_size = len(full_faults)

        csvFile = open(os.path.join(script_dir, "f_cvg.csv"), "w")
        csvFile.write("Batch #, A, B, C, D, E, seed = 1-255, Batch size = " + repr(batchSize) + "\n")
        thickness = 256  # 2 is the minmium #256 maximimum
        with concurrent.futures.ProcessPoolExecutor() as executor:
            A = executor.map(TVA_gen, map(counterGen, [seed1 for seed1 in range(1, thickness)]),
                             [inputSize for _ in range(1, thickness)])  # inputsize
            B = executor.map(TVB_gen, map(counterGen, [seed2 for seed2 in range(1, thickness)]),
                             [inputSize for _ in range(1, thickness)])
            C = executor.map(TVC_gen, map(counterGen, [seed3 for seed3 in range(1, thickness)]),
                             [inputSize for _ in range(1, thickness)])
            D = executor.map(TVD_gen, map(lfsrGen, [seed4 for seed4 in range(1, thickness)]),
                             [inputSize for _ in range(1, thickness)])
            E = executor.map(TVE_gen, map(lfsrGen, [seed5 for seed5 in range(1, thickness)]),
                             [inputSize for _ in range(1, thickness)])

        coresSize = multiprocessing.cpu_count()
        if (coresSize > 1):
            coresSize -= 1

        with concurrent.futures.ProcessPoolExecutor(max_workers=coresSize) as executor:
            data = executor.map(extreme_simulator_helper,
                                A,
                                # map(TVA_gen, map(counterGen, [seed1 for seed1 in range(1, thickness)]), [inputSize for _ in range(1, thickness)]), #A
                                B,
                                # map(TVB_gen, map(counterGen, [seed2 for seed2 in range(1, thickness)]), [inputSize for _ in range(1, thickness)]), #B
                                C,
                                # map(TVC_gen, map(counterGen, [seed3 for seed3 in range(1, thickness)]), [inputSize for _ in range(1, thickness)]), #c
                                D,
                                # map(TVD_gen, map(lfsrGen, [seed4 for seed4 in range(1, thickness)]), [inputSize for _ in range(1, thickness)]), #D
                                E,
                                # map(TVE_gen, map(lfsrGen, [seed5 for seed5 in range(1, thickness)]), [inputSize for _ in range(1, thickness)]), #E
                                [copy.deepcopy(circuit) for _ in range(1, thickness)],
                                [batchSize for _ in range(1, thickness)],
                                [full_faults for _ in range(1, thickness)],inputCycle, initDFF)  # batchsize

        detection_Avg = [[0 for _ in range(0, 25)] for _ in range(0, 5)]  # initialize the 2d array
        # all_data = open(os.path.join(script_dir, "Full_data.txt"), "w") #all_data.write("Batchsize: " + repr(batchSize) + "\n")
        for x in data:
            holdthesim = list(x)
            # all_data.write("seed: " + str(count+1) + "; \n")
            for y in range(0, 5):
                # all_data.write(str(y) + ":  " + str(holdthesim[y]) + "\n")
                for z in range(0, 25):
                    detection_Avg[y][z] += holdthesim[y][z]
        # all_data.close() #print(detection_Avg)
        for x in range(0, 5):
            for y in range(0, 25):
                detection_Avg[x][y] = detection_Avg[x][y] / (
                            thickness - 1)  # divide by the input size to get the average

        for x in range(0, 25):
            csvFile.write(
                str(x + 1) + ", " + str(round((detection_Avg[0][x] / total_fault_size) * 100, 2)) + ", " + str(
                    round((detection_Avg[1][x] / total_fault_size) * 100, 2))
                + ", " + str(round((detection_Avg[2][x] / total_fault_size) * 100, 2)) + ", " + str(
                    round((detection_Avg[3][x] / total_fault_size) * 100, 2)) + ", "
                + str(round((detection_Avg[4][x] / total_fault_size) * 100, 2)) + "\n")
        print("Time: " + str(time.perf_counter() - t1))
        csvFile.close()

    # exit()


if __name__ == "__main__":
    main()
