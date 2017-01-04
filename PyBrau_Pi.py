'''
    PyBrau_Pi.py
    
    Description: A Python TKINTER GUI for controlling the entire
                 hot side of the brewing processes from RIMS mashing
                 to boiling. GUI was designed to be used with an 
                 electric brew setup for both mashing and boiling.  
                 This verision is specifically designed for use on 
                 the offical Raspberry Pi touch screen.
    
    Revision History
    24 Sep 2016 - Created and debugged
    28 Nov 2016 - Screen size changed to fit on offical
                  Raspberry Pi screen and added buttons
                  for use without keyboard/mouse
    
    Author: Lars Soltmann
    
    Pinout: DLP-IO8-G - Pin1 - Mash kettle temperature
                        Pin2 - Mash heater temperature
                        Pin3 - Boil kettle temperature
                        Pin4 - Pump SSR
                        Pin5 - Mash heater SSR
                        Pin6 - Boil heater SSR
                        Pin7 - (Not used)
                        Pin8 - (Not used)
    
    References: N/A
    
    Notes:
    - Written for Python3
    - Tested on MacBook Pro under OSX10.11
    - Temperature sensors used are 10K NTC B57861S thermistor using a 5V voltage divider with 10K resistor
    - Thermistor wiring:
        V+ --- R10K --- Pin# --- Therm --- GND
    
    Software Requirements:
    - Python3
    - Pyserial
    - TKINTER
    
    Hardware Requirements:
    - DLP-IO8-G USB DAQ
    
    Calls:  DLP_IO8_G_py.py
            Thermistor_B57861S.py
            
            
    OPEN ITEMS:
    1. Add duty cycle optimization routine
    2. Verify that 'set' button doesn't overide automatic control, particularly DC
    
    '''


## Variables
# comms_status = 0,1 - indicates whether or not connected to USB DAQ
# pump_ON = 0,1 - indicates whether the pump is on or not
# heatM_ON = 0,1 - indicates whether the mash RIMS heating element is on or not, cannot be turned out without pump on
# heatB_ON = 0,1 - indicates whether the boil kettle heating element is on or not
# tempMK = float - mash tun kettle temperature
# setMK = int - setpoint temperature for mash tun kettle
# setMK_IN = int - input setpoint temperature for mash tun kettle
# tempMH = float - RIMS heater temperature
# tempBK = float - boil kettle temperature
# setBK = int - active setpoint temperature for boil kettle
# setBK_IN = int - input setpoint temperature for boil kettle
# boilMA = 0,1 - 0=manual control of boil element, 1=auto control of boil element
# heatB_DC_IN = int - input duty cycle for manual control of boil heater
# heatB_DC = int - duty cycle of boil heater
# heatM_DC = int - duty cycle of mash heater
# log_ON = 0,1 - data logging on or not
# DCopt= 0,1 - indicates whether duty cycle optimization algorithm is active or not
# setDC_BW = int - Duty cycle weight given to boil in optimization algorithm (0 <= x <= 1, 0.5 is equal weight between mash and boil)
# setDC_MW = int - Duty cycle weight given to mash in optimization algorithm (0 <= x <= 1, 0.5 is equal weight between mash and boil)


import tkinter as tk
import time
import sys
import math
sys.path.append('/Users/lsoltmann/CodeProjects/DLP_IO8_G') #For MAC only
from DLP_IO8_G_py import DLP
from Thermistor_B57861S import thermistor
import multiprocessing as mp


class brew_control:
    def __init__(self,master):
        self.master=master

        #Create main window of size WxH
        w=800
        h=412
        self.mainWindow = tk.Frame(self.master, width=w, height=h)
        self.master.title('Py Brau V1.0')
        self.mainWindow.pack()
        
        #Debug
        self.debug=1; #1=ON, 0=OFF, outputs all state variables to screen after any mouse event
        
        #Initialize Global-ish variables
        self.comms_status=0
        self.pump_ON=0
        self.heatM_ON=0
        self.heatB_ON=0
        self.tempMK=0
        self.tempBK=0
        self.tempMH=0
        self.boilMA=0
        self.setMK=0
        self.setMK_IN=154
        self.setBK=0
        self.setBK_IN=170
        self.heatB_DC=0
        self.heatB_DC_IN=0
        self.heatM_DC=0
        self.setDC_MW_IN=50
        self.setDC_BW_IN=50
        self.log_ON=0
        self.log_freq=1 #Hz, sample rate for data logging
        self.temp_freq=2 #Hz, sample rate for reading temperatures
        self.temp_filt_cutoff=3 #Hz, cutoff frequency for temperature filter
        self.temp_filt_coef=(2*math.pi*(1/self.temp_freq)*self.temp_filt_cutoff)/(2*math.pi*(1/self.temp_freq)*self.temp_filt_cutoff+1)
        self.first_time=1
        self.DCopt=0
        self.setDC_BW=0.5
        self.setDC_MW=0.5
        
        #Control variables
        self.DCB_T=0.5 #Duty cycle period in seconds for boil heater ***DCB_T and DCM_T should be equal
        self.DCM_T=0.5 #Duty cycle period in seconds for mash heater
        self.P_M=0.375
        self.I_M=0.09375
        self.P_B=0.375
        self.I_B=0.09375
        self.VREF=5.0
        self.THERM=thermistor()
        self.esum_M=0
        self.esum_B=0
        
        ##--- Setup multiprocessing variables ---
        #Format for data array used by multiprocessing
        #Array[0]=Pump
        #Array[1]=Mash_heater
        #Array[2]=Boil_heater
        #Array[3]=Mash_temp
        #Array[4]=Boil_temp
        #Array[5]=Mash_heater_temp
        #Array[6]=Boil_type
        #Array[7]=Mash_setpoint
        #Array[8]=Boil_setpoint
        #Array[9]=Boil_dutycycle
        #Array[10]=Mash_dutycycle
        #Array[11]=Logging frequency
        #Array[12]=error sum - mash
        #Array[13]=error sum -boil
        #Array[14]=dutcy cycle control algorithm
        #Array[15]=dutcy cycle weight, mash
        #Array[16]=dutcy cycle weight, boil
        self.data_array=mp.Array('d',[self.pump_ON,self.heatM_ON,self.heatB_ON,0.0,0.0,0.0,self.boilMA,self.setMK,self.setBK,self.heatB_DC,self.heatM_DC,self.log_freq,self.esum_M,self.esum_B,self.DCopt,self.setDC_MW,self.setDC_BW])
        self.loggingProc_EXIT=mp.Value('i', 0)
        self.boilManProc_EXIT=mp.Value('i', 0)
        self.boilAutoProc_EXIT=mp.Value('i', 0)
        self.mashProc_EXIT=mp.Value('i', 0)

        #Create all the windows
        self.init_daq_win()
        self.init_mash_win()
        self.init_boil_win()
        self.init_switch_win()
        self.init_mash_stats()
        self.init_boil_stats()
        self.init_cntrl_button_win()
        self.init_DCopt_stats()
        self.init_DCopt_ACT()
    
        #Initialize switch panel in disabled mode since no device connection has been established
        self.pump_button.config(state = 'disabled')
        self.boil_button.config(state = 'disabled')
        self.boil_type_button.config(state = 'disabled')
        self.log_button.config(state = 'disabled')
    
        ## FOR DEBUG ONLY
        self.debug_display()



    #################### USB DLP-IO8-G DAQ CONNECTION WINDOW AND BUTTON ####################
    def init_daq_win(self):
        #Window location
        win_loc_x=20
        win_loc_y=20

        #Create the subframe where the DAQ location and status are located
        subframe_daq = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)

        #Connection status light
        daq_status_light_canvas = tk.Canvas(subframe_daq,width=15,height=15)
        daq_status_light = daq_status_light_canvas.create_oval(5, 5, 15, 15,fill="red")
        daq_status_light_canvas.pack(side=tk.LEFT,padx=(5,0))

        #Connect button
        daq_connect_button = tk.Button(subframe_daq, text="Connect",command=lambda:self.connect_to_daq(daq_status_light_canvas,daq_status_light,daq_loc,daq_connect_button))
        daq_connect_button.pack(side=tk.LEFT,padx=(5,5), pady=10)


        #Entry field for device location
        daq_loc = tk.StringVar(subframe_daq, value="/dev/tty.usbserial-12345678") #Mac
        #daq_loc = tk.StringVar(subframe_daq, value="/dev/ttyUSB0")
        #daq_loc = tk.StringVar(subframe_daq, value="test") #Makes testing easier
        daq_field = tk.Entry(subframe_daq, width=25, textvariable=daq_loc).pack(side=tk.RIGHT,padx=(0,5))


        subframe_daq.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='DEVICE').place(x=win_loc_x+20, y=win_loc_y,anchor=tk.W)

    def connect_to_daq(self,daq_status_light_canvas,daq_status_light,daq_loc,daq_connect_button):
        #Open device if it wasn't previously open
        if self.comms_status==0:
            if (daq_loc.get() == "test"):
                daq_status_light_canvas.itemconfig(daq_status_light, fill="green")
                self.comms_status=1
                daq_connect_button.config(text="Disconnect")
                print('Test Mode!')
            else:
                self.DAQ=DLP(daq_loc.get())
                #If open was successful, change the status light and button text
                if self.DAQ.initialize()==0:
                    daq_status_light_canvas.itemconfig(daq_status_light, fill="green")
                    self.comms_status=1
                    daq_connect_button.config(text="Disconnect")
                    print('Device opened!')
                
                    #Make sure device is setup correctly by setting to binary and degF
                    self.DAQ.changeSettings("B","F")
                
                    ##SET ALL OUPUTS TO OFF!!
                    self.DAQ.setDigitalOutput(4,0)
                    self.DAQ.setDigitalOutput(5,0)
                    self.DAQ.setDigitalOutput(6,0)
                
                    #Make sure all process stop flags are set to run
                    self.loggingProc_EXIT.value=0
                    self.boilManProc_EXIT.value=0
                    self.boilAutoProc_EXIT.value=0
                    self.mashProc_EXIT.value=0
            
                #If open was not successfull, report error
                else:
                    daq_status_light_canvas.itemconfig(daq_status_light, fill="red")
                    self.comms_status=0
                    print('Device open error!')
        #Close device
        else:
            try:
                #Set all outputs to zero
                self.DAQ.setDigitalOutput(4,0)
                self.DAQ.setDigitalOutput(5,0)
                self.DAQ.setDigitalOutput(6,0)
                #Cancel temp loop
                self.master.after_cancel(self.temp_loop)
                self.first_time=1
                #Set all process stop flags
                self.loggingProc_EXIT.value=1
                self.heater_control_Proc_EXIT.value=1
                #End the multiprocesses if they exist
                try:
                    self.heater_control_proc.join()
                except:
                    pass
                try:
                    self.logging_proc.join()
                except:
                    pass
                #Disconnect from device
                self.DAQ.disconnect()
                self.comms_status=0
                print('Device closed!')
            except:
                print('Could not close device ... or exiting test mode.')
                self.comms_status=0
            daq_status_light_canvas.itemconfig(daq_status_light, fill="red")
            daq_connect_button.config(text="Connect")

        if self.comms_status==1:
            #If comms were successfully established, enable all buttons except mash (requires pump to be ON)
            self.pump_button.config(state = 'active')
            self.boil_button.config(state = 'active')
            self.boil_type_button.config(state = 'active')
            self.log_button.config(state = 'active')
            self.read_all_temps()
        elif self.comms_status==0:
            #If comms are closed, set all buttons to OFF and disable them
            self.pump_button.config(state = 'disabled')
            self.pump_button.config(text="PUMP      <OFF>  ON",justify=tk.LEFT)
            self.pump_ON=0
            self.data_array[0]=self.pump_ON
            self.subcanvas_mash.itemconfig(self.mash_pump_text, text='OFF',fill='black')
            self.subcanvas_mash.itemconfig(self.mash_pump_box,fill='white')
            self.stat_pump_ON.set('OFF')
            self.boil_button.config(state = 'disabled')
            self.boil_button.config(text="BOIL      <OFF>  ON",justify=tk.LEFT)
            self.heatB_ON=0
            self.data_array[2]=self.heatB_ON
            self.data_array[10]=0
            self.boil_type_button.config(state = 'disabled')
            self.stat_heatB_ON.set('OFF')
            self.mash_button.config(state = 'disabled')
            self.mash_button.config(text="MASH      <OFF>  ON",justify=tk.LEFT)
            self.heatM_ON=0
            self.data_array[1]=self.heatM_ON
            self.subcanvas_mash.itemconfig(self.mash_heater_color1,fill='white')
            self.stat_heatM_ON.set('OFF')
            self.heatB_DC=0
            self.data_array[9]=self.heatB_DC
            self.stat_heatB_DC.set(self.heatB_DC)
            self.log_button.config(text="DATA LOG      <OFF>  ON",justify=tk.LEFT)
            self.log_button.config(state = 'disabled')
            self.log_ON=0
        ## FOR DEBUG ONLY
        self.debug_display()


    #################### SWITCH PANEL ####################
    def init_switch_win(self):
        #Window location
        win_loc_x=450
        win_loc_y=20
        
        #Create the subframe where the all the switches are
        subframe_switchPanel = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
    
        #Mash ON/OFF button
        self.mash_button = tk.Button(subframe_switchPanel, text="MASH      <OFF>  ON",justify=tk.LEFT,wraplength=70,state = 'disabled',command=lambda:self.mash_command(self.mash_button))
        self.mash_button.grid(column = 0, row = 0, pady=10)
        #PUMP ON/OFF button
        self.pump_button = tk.Button(subframe_switchPanel, text="PUMP      <OFF>  ON",justify=tk.LEFT,wraplength=70,command=lambda:self.pump_command(self.pump_button,self.mash_button))
        self.pump_button.grid(column = 1, row = 0, pady=10)
        #BOIL ON/OFF button
        self.boil_button = tk.Button(subframe_switchPanel, text="BOIL      <OFF>  ON",justify=tk.LEFT,wraplength=70,command=lambda:self.boil_command(self.boil_button))
        self.boil_button.grid(column = 2, row = 0, pady=10)
        #BOIL auto/manual button
        self.boil_type_button = tk.Button(subframe_switchPanel, text="BOIL CNTL         <MAN>  AUTO",justify=tk.LEFT,wraplength=100,command=lambda:self.boil_type_command(self.boil_type_button))
        self.boil_type_button.grid(column = 0, row = 1)
        #Data Logging button
        self.log_button = tk.Button(subframe_switchPanel, text="DATA LOG      <OFF>  ON",justify=tk.LEFT,wraplength=70,command=lambda:self.log_command(self.log_button))
        self.log_button.grid(column = 1, row = 1)
    
        subframe_switchPanel.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='SWITCH PANEL').place(x=win_loc_x+20, y=win_loc_y,anchor=tk.W)

    
    ########### SWITCH PANEL FUNCTIONS ###########
    # Master mash button
    def mash_command(self,mash_button):
        #Mash can only be turned ON if the pump is ON
        if self.pump_ON==1 and self.heatM_ON==0:
            mash_button.config(text="MASH       OFF  <ON>",justify=tk.LEFT)
            self.heatM_ON=1
            self.subcanvas_mash.itemconfig(self.mash_heater_color1,fill='red')
            self.stat_heatM_ON.set('ON')
        elif self.heatM_ON==1:
            mash_button.config(text="MASH      <OFF>  ON",justify=tk.LEFT)
            self.heatM_ON=0
            self.subcanvas_mash.itemconfig(self.mash_heater_color1,fill='white')
            self.stat_heatM_ON.set('OFF')
            self.esum_M=0
            self.data_array[12]=self.esum_M
        
        # Start/stop mash process
        self.data_array[1]=self.heatM_ON
        self.mash_StartStop()
        
        ## FOR DEBUG ONLY
        self.debug_display()

    # Master boil button
    def boil_command(self,boil_button):
        if self.heatB_ON==0:
            boil_button.config(text="BOIL       OFF  <ON>",justify=tk.LEFT)
            self.heatB_ON=1
            self.stat_heatB_ON.set('ON')
        elif self.heatB_ON==1:
            boil_button.config(text="BOIL      <OFF>  ON",justify=tk.LEFT)
            self.heatB_ON=0
            self.stat_heatB_ON.set('OFF')
        
        # Start/stop boil process
        self.data_array[2]=self.heatB_ON
        self.boil_StartStop()
        
        ## FOR DEBUG ONLY
        self.debug_display()

    # Pump button
    def pump_command(self,pump_button,mash_button):
        if self.pump_ON==0:
            pump_button.config(text="PUMP       OFF  <ON>",justify=tk.LEFT)
            self.pump_ON=1
            mash_button.config(state = 'active')
            self.stat_pump_ON.set('ON')
            self.subcanvas_mash.itemconfig(self.mash_pump_text, text='ON',fill='black')#,fill='green')
            self.subcanvas_mash.itemconfig(self.mash_pump_box,fill='green')
            self.DAQ.setDigitalOutput(4,1)
        elif self.pump_ON==1:
            #Automatically turn OFF mash heater if pump is turned OFF
            pump_button.config(text="PUMP      <OFF>  ON",justify=tk.LEFT)
            mash_button.config(text="MASH      <OFF>  ON",justify=tk.LEFT)
            self.pump_ON=0
            self.heatM_ON=0
            mash_button.config(state = 'disabled')
            self.subcanvas_mash.itemconfig(self.mash_pump_text, text='OFF',fill='black')
            self.subcanvas_mash.itemconfig(self.mash_pump_box,fill='white')
            self.subcanvas_mash.itemconfig(self.mash_heater_color1,fill='white')
            self.stat_pump_ON.set('OFF')
            self.stat_heatM_ON.set('OFF')
            self.DAQ.setDigitalOutput(4,0)
        
        self.data_array[0]=self.pump_ON
        self.data_array[1]=self.heatM_ON
        self.mash_StartStop()
        
        ## FOR DEBUG ONLY
        self.debug_display()

    # Boil manual/auto button
    def boil_type_command(self,boil_type_button):
        if self.boilMA==0:
            boil_type_button.config(text="BOIL CNTL           MAN  <AUTO>",justify=tk.LEFT)
            self.boilMA=1
            self.heatB_DC=0
            self.stat_boilMA.set('AUTO')
            self.stat_heatB_DC.set(self.heatB_DC)
        elif self.boilMA==1:
            boil_type_button.config(text="BOIL CNTL          <MAN>  AUTO",justify=tk.LEFT)
            self.boilMA=0
            self.stat_boilMA.set('MAN')

        # Change the boil process if it was active
        self.data_array[2]=self.heatB_ON
        self.data_array[6]=self.boilMA
        self.data_array[9]=self.heatB_DC
        self.boil_StartStop()

        ## FOR DEBUG ONLY
        self.debug_display()
    
    # Data logging button
    def log_command(self,log_button):
        if self.log_ON==0:
            log_button.config(text="DATA LOG      OFF  <ON>",justify=tk.LEFT)
            self.log_ON=1
        elif self.log_ON==1:
            log_button.config(text="DATA LOG      <OFF>  ON",justify=tk.LEFT)
            self.log_ON=0
        
        #Setup/manage log file
        self.logging_StartStop()
        
        ## FOR DEBUG ONLY
        self.debug_display()

    #################### BUTTON PANEL FOR TEMP/DC CONTROL ####################
    def init_cntrl_button_win(self):
        #Window location
        win_loc_x=13
        win_loc_y=320
        
        #Create the subframe where the all the switches are
        self.subframe_buttonPanel = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        
        #Mash Temp Label
        self.mash_button_label=tk.Label(self.subframe_buttonPanel, text='MASH')
        self.mash_button_label.grid(row=0,column=0,columnspan=2,pady=(5,0))
        #Mash Temp +10 button
        self.mash_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_p10())
        self.mash_p10_button.grid(column = 0, row = 1,padx=(5,0))
        #Mash Temp -10 button
        self.mash_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_m10())
        self.mash_m10_button.grid(column = 0, row = 2,padx=(5,0))
        #Mash Temp +1 button
        self.mash_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_p1())
        self.mash_p1_button.grid(column = 1, row = 1)
        #Mash Temp -1 button
        self.mash_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_m1())
        self.mash_m1_button.grid(column = 1, row = 2)
        
        #Boil Temp Label
        self.boil_button_label=tk.Label(self.subframe_buttonPanel, text='BOIL')
        self.boil_button_label.grid(row=0,column=2,columnspan=2,pady=(5,0))
        #Boil Temp +10 button
        self.boil_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_p10())
        self.boil_p10_button.grid(column = 2, row = 1,padx=(5,0))
        #Boil Temp -10 button
        self.boil_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_m10())
        self.boil_m10_button.grid(column = 2, row = 2,padx=(5,0))
        #Boil Temp +1 button
        self.boil_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_p1())
        self.boil_p1_button.grid(column = 3, row = 1)
        #Boil Temp -1 button
        self.boil_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_m1())
        self.boil_m1_button.grid(column = 3, row = 2)
        
        #DC Temp Label
        self.dc_button_label=tk.Label(self.subframe_buttonPanel, text='DC')
        self.dc_button_label.grid(row=0,column=4,columnspan=2,pady=(5,0))
        #DC +10 button
        self.dc_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_p10())
        self.dc_p10_button.grid(column = 4, row = 1, padx=(5,0))
        #DC -10 button
        self.dc_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_m10())
        self.dc_m10_button.grid(column = 4, row = 2, padx=(5,0))
        #DC +1 button
        self.dc_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_p1())
        self.dc_p1_button.grid(column = 5, row = 1)
        #DC -1 button
        self.dc_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_m1())
        self.dc_m1_button.grid(column = 5, row = 2)
        
        #Weighting critiera for duty cycle control optimization
        #DC Weight Label
        self.dcw_button_label=tk.Label(self.subframe_buttonPanel, text='DC Wt')
        self.dcw_button_label.grid(row=0,column=6,columnspan=2,pady=(5,0))
        #DC_W +10 button
        self.dcw_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_DC_W_p10())
        self.dcw_p10_button.grid(column = 6, row = 1, padx=(5,0))
        #DC_W -10 button
        self.dcw_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_DC_W_m10())
        self.dcw_m10_button.grid(column = 6, row = 2, padx=(5,0))
        #DC_W +1 button
        self.dcw_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_DC_W_p1())
        self.dcw_p1_button.grid(column = 7, row = 1)
        #DC_W -1 button
        self.dcw_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_DC_W_m1())
        self.dcw_m1_button.grid(column = 7, row = 2)
        
        #Set all inputs button
        self.set_inputs_button = tk.Button(self.subframe_buttonPanel, text="SET   ",justify=tk.CENTER,wraplength=30,command=lambda:self.set_all_inputs_cmd())
        self.set_inputs_button.grid(column = 8, row=1,rowspan=2,sticky=tk.N+tk.S,pady=(2,0),padx=(5,5))
        
        self.subframe_buttonPanel.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='CONTROL PANEL').place(x=win_loc_x+20, y=win_loc_y,anchor=tk.W)
    
    #################### BUTTON PANEL FUNCTIONS ####################
    #BOIL
    def input_boil_setpoint_p10(self):
        # Increase boil temperature by 10degF and limit to 212
        self.setBK_IN=self.setBK_IN+10
        if self.setBK_IN>=212:
            self.setBK_IN=212
        self.stat_inBK.set(self.setBK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()
    
    def input_boil_setpoint_m10(self):
        # Decrease boil temperature by 10degF and limit to 70
        self.setBK_IN=self.setBK_IN-10
        if self.setBK_IN<=70:
            self.setBK_IN=70
        self.stat_inBK.set(self.setBK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    def input_boil_setpoint_p1(self):
        # Increase boil temperature by 1degF and limit to 212
        self.setBK_IN=self.setBK_IN+1
        if self.setBK_IN>=212:
            self.setBK_IN=212
        self.stat_inBK.set(self.setBK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()
    
    def input_boil_setpoint_m1(self):
        # Decrease boil temperature by 1degF and limit to 70
        self.setBK_IN=self.setBK_IN-1
        if self.setBK_IN<=70:
            self.setBK_IN=70
        self.stat_inBK.set(self.setBK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    #DUTY CYCLE
    def input_DC_setpoint_p10(self):
        # Increase boil duty cycle by 10% and limit to 100
        self.heatB_DC_IN=self.heatB_DC_IN+10
        if self.heatB_DC_IN>=100:
            self.heatB_DC_IN=100
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ## FOR DEBUG ONLY
        self.debug_display()
    
    def input_DC_setpoint_m10(self):
        # Decrease boil duty cycle by 10% and limit to 0
        self.heatB_DC_IN=self.heatB_DC_IN-10
        if self.heatB_DC_IN<=0:
            self.heatB_DC_IN=0
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    def input_DC_setpoint_p1(self):
        # Increase boil duty cycle by 1% and limit to 100
        self.heatB_DC_IN=self.heatB_DC_IN+1
        if self.heatB_DC_IN>=100:
            self.heatB_DC_IN=100
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ## FOR DEBUG ONLY
        self.debug_display()
    
    def input_DC_setpoint_m1(self):
        # Decrease boil duty cycle by 1% and limit to 0
        self.heatB_DC_IN=self.heatB_DC_IN-1
        if self.heatB_DC_IN<=0:
            self.heatB_DC_IN=0
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    #MASH
    def input_mash_setpoint_p10(self):
        # Increase mash temperature by 10degF and limit to 180
        self.setMK_IN=self.setMK_IN+10
        if self.setMK_IN>=180:
            self.setMK_IN=180
        self.stat_inMK.set(self.setMK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()
    
    def input_mash_setpoint_m10(self):
        # Decrease mash temperature by 10degF and limit to 70
        self.setMK_IN=self.setMK_IN-10
        if self.setMK_IN<=70:
            self.setMK_IN=70
        self.stat_inMK.set(self.setMK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    def input_mash_setpoint_p1(self):
        # Increase mash temperature by 1degF and limit to 180
        self.setMK_IN=self.setMK_IN+1
        if self.setMK_IN>=180:
            self.setMK_IN=180
        self.stat_inMK.set(self.setMK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()
    
    def input_mash_setpoint_m1(self):
        # Decrease mash temperature by 1degF and limit to 70
        self.setMK_IN=self.setMK_IN-1
        if self.setMK_IN<=70:
            self.setMK_IN=70
        self.stat_inMK.set(self.setMK_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    #DC Weight
    def input_DC_W_p10(self):
        # Increase duty cycle optimization mash weight by 10% and limit to 99%
        self.setDC_MW_IN=self.setDC_MW_IN+10
        if self.setDC_MW_IN>=99:
            self.setDC_MW_IN=99
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    def input_DC_W_m10(self):
        # Decrease duty cycle optimization mash weight by 10% and limit to 1%
        self.setDC_MW_IN=self.setDC_MW_IN-10
        if self.setDC_MW_IN<=1:
            self.setDC_MW_IN=1
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    def input_DC_W_p1(self):
        # Increase duty cycle optimization mash weight by 1% and limit to 99%
        self.setDC_MW_IN=self.setDC_MW_IN+1
        if self.setDC_MW_IN>=99:
            self.setDC_MW_IN=99
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    def input_DC_W_m1(self):
        # Decrease duty cycle optimization mash weight by 1% and limit to 1%
        self.setDC_MW_IN=self.setDC_MW_IN-1
        if self.setDC_MW_IN<=1:
            self.setDC_MW_IN=1
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ## FOR DEBUG ONLY
        self.debug_display()

    #### SET ALL INPUTS
    def set_all_inputs_cmd(self):
        # Set variables
        self.setMK=self.setMK_IN
        self.data_array[7]=self.setMK
        self.setBK=self.setBK_IN
        self.data_array[8]=self.setBK
        self.heatB_DC=self.heatB_DC_IN
        self.data_array[9]=self.heatB_DC
        self.setDC_MW=self.setDC_MW_IN/100
        self.data_array[15]=self.setDC_MW
        self.setDC_BW=(100-self.setDC_MW_IN)/100
        self.data_array[16]=self.setDC_BW
        
        # Update the gui
        self.stat_setMK.set(self.setMK)
        self.stat_setBK.set(self.setBK)
        self.stat_heatB_DC.set(self.heatB_DC)
        self.stat_setDCMW.set(self.setDC_MW_IN)
        self.stat_setDCBW.set(100-self.setDC_MW_IN)
        
        ## FOR DEBUG ONLY
        self.debug_display()



    #################### MASH WINDOW ####################
    def init_mash_win(self):
        #Window location
        win_loc_x=10
        win_loc_y=95
        Kshift=80
        WK=150
        HK=150
        BW=6 #simulated border width
        FC=1
        
        #Create the subframe where all mash related items go
        self.subframe_mash = tk.Frame(self.master, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        #Create canvas for mash graphics
        self.subcanvas_mash=tk.Canvas(self.subframe_mash,width=270,height=215)
        
        #Place the mash canvas
        self.subframe_mash.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='MASH').place(x=win_loc_x+Kshift+WK/2, y=win_loc_y-10,anchor=tk.CENTER)

        ##Draw simulated mash system
        BW1=6
        W1=65
        H1=35
        FC1=1
        x1=0
        y1=(HK-H1/2)/2
        x2=W1
        y2=(HK-H1/2)/2+H1
        #Heater lines
        self.subcanvas_mash.create_line(x2-5,(y1+y2)/2,Kshift,(y1+y2)/2,width=5)# Added 5 is to make sure there is overlap
        self.subcanvas_mash.create_line((x1+x2)/2,y2-5,(x1+x2)/2,y2+70,width=5)# Subtracted 5 is to make sure there is overlap
        self.subcanvas_mash.create_line((x1+x2)/2-2,y2+70,Kshift+WK/2,y2+70,width=5)# Subtracted 5 is to make sure there is overlap
        self.subcanvas_mash.create_line(Kshift+WK/2,y2+70+2,Kshift+WK/2,HK-5,width=5)# Subtracted 5 is to make sure there is overlap
        #Heater + temp
        self.mash_heater_loc_x=(x1+x2)/2 #location of temp heater label on mash canvas, x
        self.mash_heater_loc_y=(y1+y2)/2 #location of temp heater label on mash canvas, y
        self.subcanvas_mash.create_rectangle(x1,y1,x2,y2,outline='black',width=0,fill='black') #simulated border for heater temperature
        self.mash_heater_color1=self.subcanvas_mash.create_rectangle(x1+BW1+2,y1+BW1,x2-BW1,y1+H1-BW1,outline='black',width=0,fill='white') #mash heater 'text' box
        self.mash_heater_color2=self.subcanvas_mash.create_text(self.mash_heater_loc_x,self.mash_heater_loc_y,text=self.tempMH,fill='black',anchor=tk.CENTER)
        self.subcanvas_mash.create_text((x1+x2)/2,y1-10,text='Heater',fill='black',anchor=tk.CENTER) #label
        #Pump + status
        self.subcanvas_mash.create_rectangle(x1,y1+70+H1/2,x2,y2+70+H1/2,outline='black',width=0,fill='black') #simulated border for pump
        self.mash_pump_box=self.subcanvas_mash.create_rectangle(x1+BW1+2,y1+BW1+70+H1/2,x2-BW1,y1+H1-BW1+70+H1/2,outline='black',width=0,fill='white') #pump 'text' box
        self.mash_pump_text=self.subcanvas_mash.create_text((x1+x2)/2,(y1+y2)/2+70+H1/2,text='OFF',fill='black',anchor=tk.CENTER)
        self.subcanvas_mash.create_text((x1+x2)/2,y1+70+H1+27,text='Pump',fill='black',anchor=tk.CENTER) #label
        #Mash tun
        self.mash_tun_loc_x=Kshift+WK/2 #location of mash temp label on mash canvas, x
        self.mash_tun_loc_y=(((HK-2*BW)/3)/2)+BW #location of mast temp label on mash canvas, y
        self.subcanvas_mash.create_rectangle(Kshift,0,Kshift+WK,HK,outline='black',width=0,fill='black') #simulated border
        self.subcanvas_mash.create_rectangle(Kshift+BW,0+BW+2,Kshift+WK-BW*FC,(HK-2*BW)/3+BW,outline='black',width=0,fill='#ececec') #simulated air
        self.mash_water_color=self.subcanvas_mash.create_rectangle(Kshift+BW,(HK-2*BW)/3+BW,Kshift+WK-BW*FC,HK-BW*FC,outline='black',width=0,fill='blue') #simulated water
        self.mash_tolerance=self.subcanvas_mash.create_rectangle(Kshift+WK/2-W1/2+x1+BW1,(((HK-2*BW)/3)/2)+BW-H1/3,Kshift+WK/2-W1/2+x2-BW1,(((HK-2*BW)/3)/2)+BW+H1/3,outline='black',width=0,fill='red') #temperature tolerance indicator box
        self.mash_temp_color=self.subcanvas_mash.create_text(self.mash_tun_loc_x,self.mash_tun_loc_y,text=self.tempMK,fill='black',anchor=tk.CENTER)
        self.subcanvas_mash.pack()
    
    
    #################### MASH STATS ####################
    def init_mash_stats(self):
        #Window location
        win_loc_x=430
        win_loc_y=150
        
        self.subframe_mash_stats = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        tk.Label(self.subframe_mash_stats, text="Setpoint-IN:",foreground="blue").grid(row=0,column=0,padx=(5,5),pady=(5,0),sticky=tk.E)
        tk.Label(self.subframe_mash_stats, text="Setpoint-ACT:").grid(row=1,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_mash_stats, text="Mash Temp:").grid(row=2,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_mash_stats, text="Heater Temp:").grid(row=3,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_mash_stats, text="Heater Status:").grid(row=4,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_mash_stats, text="Heater DC:").grid(row=5,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_mash_stats, text="Pump Status:").grid(row=6,column=0,padx=(5,5),sticky=tk.E)
        
        self.stat_inMK=tk.StringVar(self.subframe_mash_stats,value=self.setMK_IN)
        self.mash_stat_INsetpoint_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_inMK,foreground="blue")
        self.mash_stat_INsetpoint_label.grid(row=0,column=1,pady=(5,0))

        self.stat_setMK=tk.StringVar(self.subframe_mash_stats,value=self.setMK)
        self.mash_stat_setpoint_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_setMK)
        self.mash_stat_setpoint_label.grid(row=1,column=1)
        
        self.stat_tempMK=tk.StringVar(self.subframe_mash_stats,value=self.tempMK)
        self.mash_stat_tempM_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_tempMK)
        self.mash_stat_tempM_label.grid(row=2,column=1)
        
        self.stat_tempMH=tk.StringVar(self.subframe_mash_stats,value=self.tempMH)
        self.mash_stat_tempH_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_tempMH)
        self.mash_stat_tempH_label.grid(row=3,column=1)
        
        self.stat_heatM_ON=tk.StringVar(self.subframe_mash_stats,value='OFF')
        self.mash_stat_heatON_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_heatM_ON)
        self.mash_stat_heatON_label.grid(row=4,column=1)
        
        self.stat_heatM_DC=tk.StringVar(self.subframe_mash_stats,value=self.heatM_DC)
        self.mash_stat_heatDC_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_heatM_DC)
        self.mash_stat_heatDC_label.grid(row=5,column=1)
        
        self.stat_pump_ON=tk.StringVar(self.subframe_mash_stats,value='OFF')
        self.mash_stat_pump_label=tk.Label(self.subframe_mash_stats, textvariable=self.stat_pump_ON)
        self.mash_stat_pump_label.grid(row=6,column=1)
    
        self.subframe_mash_stats.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='MASH STATS').place(x=win_loc_x+33, y=win_loc_y,anchor=tk.W)
    

    #################### BOIL WINDOW ####################
    def init_boil_win(self):
        #Window location
        win_loc_x=260
        win_loc_y=95#320
        
        WK=150
        HK=150
        BW=6 #simulated border width
        FC=1
        
        BW1=6
        W1=65
        H1=35
        FC1=1
        x1=0
        y1=(HK-H1/2)/2
        x2=W1
        y2=(HK-H1/2)/2+H1
        
        self.boil_kettle_loc_x=WK/2
        self.boil_kettle_loc_y=(((HK-2*BW1)/3)/2)+BW1
        
        #Create the subframe where all boil related items go
        self.subframe_boil = tk.Frame(self.master, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        #Create canvas for boil graphics
        self.subcanvas_boil=tk.Canvas(self.subframe_boil)
        #Place the boil canvas
        self.subframe_boil.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='BOIL').place(x=win_loc_x+(WK/2), y=win_loc_y-10,anchor=tk.CENTER)
        
        #Draw simulated boil kettle
        self.subcanvas_boil.create_rectangle(0,0,WK,HK,outline='black',width=0,fill='black') #simulated border
        self.subcanvas_boil.create_rectangle(0+BW1+3,0+BW1+3,WK-BW1*FC,(HK-2*BW1)/3+BW1,outline='black',width=0,fill='#ececec') #simulated air
        self.boil_water_color=self.subcanvas_boil.create_rectangle(0+BW1+3,(HK-2*BW1)/3+BW1,WK-BW1*FC,HK-BW1*FC,outline='black',width=0,fill='blue') #simulated water
        self.boil_tolerance=self.subcanvas_boil.create_rectangle(WK/2-W1/2+x1+BW1,(((HK-2*BW)/3)/2)+BW-H1/3,WK/2-W1/2+x2-BW1,(((HK-2*BW)/3)/2)+BW+H1/3,outline='black',width=0,fill='red') #temperature tolerance indicator box
        self.boil_temp_color=self.subcanvas_boil.create_text(self.boil_kettle_loc_x,self.boil_kettle_loc_y,text=self.tempBK,fill='black',anchor=tk.CENTER)
        self.subcanvas_boil.pack()


    #################### BOIL STATS ####################
    def init_boil_stats(self):
        #Window location
        win_loc_x=605
        win_loc_y=150
        
        self.subframe_boil_stats = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        tk.Label(self.subframe_boil_stats, text="Setpoint-IN:",foreground="blue").grid(row=0,column=0,padx=(5,5),pady=(5,0),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Setpoint-ACT:").grid(row=1,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Boil Temp:").grid(row=2,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Control Mode:").grid(row=3,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater Status:").grid(row=4,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater DC-IN:",foreground="blue").grid(row=5,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater DC-ACT:").grid(row=6,column=0,padx=(5,5),sticky=tk.E)
        
        self.stat_inBK=tk.StringVar(self.subframe_boil_stats,value=self.setBK_IN)
        self.boil_stat_INsetpoint_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_inBK,foreground="blue")
        self.boil_stat_INsetpoint_label.grid(row=0,column=1,pady=(5,0))
        
        self.stat_setBK=tk.StringVar(self.subframe_boil_stats,value=self.setBK)
        self.boil_stat_setpoint_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_setBK)
        self.boil_stat_setpoint_label.grid(row=1,column=1)
        
        self.stat_tempBK=tk.StringVar(self.subframe_boil_stats,value=self.tempBK)
        self.boil_stat_tempB_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_tempBK)
        self.boil_stat_tempB_label.grid(row=2,column=1)
        
        self.stat_boilMA=tk.StringVar(self.subframe_boil_stats,value='MAN')
        self.boil_stat_boilMA_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_boilMA)
        self.boil_stat_boilMA_label.grid(row=3,column=1)
        
        self.stat_heatB_ON=tk.StringVar(self.subframe_boil_stats,value='OFF')
        self.boil_stat_heatON_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_heatB_ON)
        self.boil_stat_heatON_label.grid(row=4,column=1)
        
        self.stat_inheatB_DC=tk.StringVar(self.subframe_boil_stats,value=self.heatB_DC_IN)
        self.boil_stat_INheatDC_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_inheatB_DC,foreground="blue")
        self.boil_stat_INheatDC_label.grid(row=5,column=1)
        
        self.stat_heatB_DC=tk.StringVar(self.subframe_boil_stats,value=self.heatB_DC)
        self.boil_stat_heatDC_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_heatB_DC)
        self.boil_stat_heatDC_label.grid(row=6,column=1)
        
        self.subframe_boil_stats.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='BOIL STATS').place(x=win_loc_x+35, y=win_loc_y,anchor=tk.W)
    
    
    #################### DC OPTIMIZATION STATS ####################
    def init_DCopt_stats(self):
        #Window location
        win_loc_x=508
        win_loc_y=335
        
        self.subframe_DCopt_stats = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        tk.Label(self.subframe_DCopt_stats, text="Boil Wt-IN:",foreground="blue").grid(row=0,column=2,padx=(5,0),pady=(5,0),sticky=tk.E)
        tk.Label(self.subframe_DCopt_stats, text="Boil Wt-ACT:").grid(row=1,column=2,padx=(5,0),sticky=tk.E)
        tk.Label(self.subframe_DCopt_stats, text="Mash Wt-IN:",foreground="blue").grid(row=0,column=0,padx=(5,0),pady=(5,0),sticky=tk.E)
        tk.Label(self.subframe_DCopt_stats, text="Mash Wt-ACT:").grid(row=1,column=0,padx=(5,0),sticky=tk.E)
        
        self.stat_inDCBW=tk.StringVar(self.subframe_DCopt_stats,value=int(self.setDC_BW*100))
        self.DCopt_stat_inBW_label=tk.Label(self.subframe_DCopt_stats, textvariable=self.stat_inDCBW,foreground="blue")
        self.DCopt_stat_inBW_label.grid(row=0,column=3,pady=(5,0))
        
        self.stat_setDCBW=tk.StringVar(self.subframe_DCopt_stats,value=self.setDC_BW_IN)
        self.DCopt_stat_setBW_label=tk.Label(self.subframe_DCopt_stats, textvariable=self.stat_setDCBW)
        self.DCopt_stat_setBW_label.grid(row=1,column=3)
        
        self.stat_inDCMW=tk.StringVar(self.subframe_DCopt_stats,value=int(self.setDC_MW*100))
        self.DCopt_stat_inMW_label=tk.Label(self.subframe_DCopt_stats, textvariable=self.stat_inDCMW,foreground="blue")
        self.DCopt_stat_inMW_label.grid(row=0,column=1,pady=(5,0))
        
        self.stat_setDCMW=tk.StringVar(self.subframe_DCopt_stats,value=self.setDC_MW_IN)
        self.DCopt_stat_setMW_label=tk.Label(self.subframe_DCopt_stats, textvariable=self.stat_setDCMW)
        self.DCopt_stat_setMW_label.grid(row=1,column=1)
    
        self.subframe_DCopt_stats.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='DUTY CYCLE OPT').place(x=win_loc_x+35, y=win_loc_y,anchor=tk.W)
    
    #################### DC OPTIMIZATION STATS ####################
    def init_DCopt_ACT(self):
        #Window location
        win_loc_x=210
        win_loc_y=260
        
        self.subframe_DCopt_act = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        tk.Label(self.subframe_DCopt_act, text="DC Optimization:").grid(row=0,column=0,padx=(10,0),pady=(10,10))
    
        self.stat_DCopt_act=tk.StringVar(self.subframe_DCopt_act,value='OFF')
        self.stat_DCopt_act_label=tk.Label(self.subframe_DCopt_act, textvariable=self.stat_DCopt_act,foreground="red")
        self.stat_DCopt_act_label.grid(row=0,column=1,padx=(0,10),pady=(10,10))
    
        self.subframe_DCopt_act.place(x=win_loc_x, y=win_loc_y)


################################################ CONTROL/FLOW FUNCTIONS ###############################################
    ## PI control to determine duty cycle for both mash and boil controls
    def PI_ctrl(self,SP,PV,kp,ki,esum):
        #SP=setpoint
        #PV=process variable
        #kp=proportional gain
        #ki=integral gain
        #esum=error sum
        
        ##Calculate duty cycle for heater
        error=SP-PV
        esum=esum+(error*self.DCM_T)
        # Limit the integrator to prevent windup
        if esum>5.0:
            esum=5.0
        elif esum<-5.0:
            esum=-5.0
        P=kp*error
        I=ki*esum
        u=P+I
        # Limit output to between 0 and 1
        if u>1.0:
            u=1.0
        elif u<0.0:
            u=0.0
        u=u*100 #Bring the duty cycle back to a value between 0 and 100.  This is only done for the dispaly and logging purpose.  The PID gains were orignially used with a 0 to 1 output so the that part of the algorithm will not be changed and just the final duty cycle brough up by two orders of magnitude.
        return u,esum
    
    ## Temperature reading/GUI updating loop
    def read_all_temps(self):
        t1=time.time()
        
        # Read temperatures
        tempMK_volts=self.DAQ.getVoltage(1)
        tempMH_volts=self.DAQ.getVoltage(2)
        tempBK_volts=self.DAQ.getVoltage(3)
        tempMK_raw=self.THERM.getTempF(10000,self.VREF,tempMK_volts)
        tempMH_raw=self.THERM.getTempF(10000,self.VREF,tempMH_volts)
        tempBK_raw=self.THERM.getTempF(10000,self.VREF,tempBK_volts)
        
        if self.first_time==1:
            self.tempMK=tempMK_raw
            self.tempMH=tempMH_raw
            self.tempBK=tempBK_raw
            self.first_time=0
        
        # Apply exponential moving average filter to temperature data
        self.tempMK=self.temp_filt_coef*tempMK_raw+(1-self.temp_filt_coef)*self.tempMK
        self.tempMH=self.temp_filt_coef*tempMH_raw+(1-self.temp_filt_coef)*self.tempMH
        self.tempBK=self.temp_filt_coef*tempBK_raw+(1-self.temp_filt_coef)*self.tempBK
        
        self.data_array[3]=self.tempMK
        self.data_array[5]=self.tempMH
        self.data_array[4]=self.tempBK
        
        ## Update all temperature labels
        #
        self.subcanvas_mash.delete(self.mash_heater_color2) # Update the mash heater temp in mash canvas
        self.mash_heater_color2=self.subcanvas_mash.create_text(self.mash_heater_loc_x,self.mash_heater_loc_y,text='{:.1f}'.format(self.tempMH),fill='black',anchor=tk.CENTER)

        self.subcanvas_mash.delete(self.mash_temp_color) # Update the mash kettle temp in mash canvas
        self.mash_temp_color=self.subcanvas_mash.create_text(self.mash_tun_loc_x,self.mash_tun_loc_y,text='{:.1f}'.format(self.tempMK),fill='black',anchor=tk.CENTER)
        
        #Tolerance box color of mash kettle
        # +/-0.5deg = green, +/-0.5 to +/-1deg = yellow, >+/-1deg = red
        if abs(self.tempMK-self.setMK)>1:
            self.subcanvas_mash.itemconfig(self.mash_tolerance,fill='red')
        elif abs(self.tempMK-self.setMK)>0.5 and abs(self.tempMK-self.setMK)<=1:
            self.subcanvas_mash.itemconfig(self.mash_tolerance,fill='yellow')
        else:
            self.subcanvas_mash.itemconfig(self.mash_tolerance,fill='green')
        
        #Change the mash kettle water color based on temperature
        if self.tempMK<=100:
            self.subcanvas_mash.itemconfig(self.mash_water_color,fill='#0000FF')
        elif self.tempMK<=120:
            self.subcanvas_mash.itemconfig(self.mash_water_color,fill='#7F00FF')
        elif self.tempMK<=140:
            self.subcanvas_mash.itemconfig(self.mash_water_color,fill='#FF00FF')
        elif self.tempMK<=160:
            self.subcanvas_mash.itemconfig(self.mash_water_color,fill='#FF007F')
        elif self.tempMK>=180:
            self.subcanvas_mash.itemconfig(self.mash_water_color,fill='#FF0000')

        self.subcanvas_boil.delete(self.boil_temp_color) # Update the boil kettle temp in boil canvas
        self.boil_temp_color=self.subcanvas_boil.create_text(self.boil_kettle_loc_x,self.boil_kettle_loc_y,text='{:.1f}'.format(self.tempBK),fill='black',anchor=tk.CENTER)
        
        #Tolerance box color of boil kettle
        # +/-0.5deg = green, +/-0.5 to +/-1deg = yellow, >+/-1deg = red
        if abs(self.tempBK-self.setBK)>1:
            self.subcanvas_boil.itemconfig(self.boil_tolerance,fill='red')
        elif abs(self.tempBK-self.setBK)>0.5 and abs(self.tempBK-self.setBK)<=1:
            self.subcanvas_boil.itemconfig(self.boil_tolerance,fill='yellow')
        else:
            self.subcanvas_boil.itemconfig(self.boil_tolerance,fill='green')

        #Change the boil kettle water color based on temperature
        if self.tempMK<=100:
            self.subcanvas_boil.itemconfig(self.boil_water_color,fill='#0000FF')
        elif self.tempMK<=120:
            self.subcanvas_boil.itemconfig(self.boil_water_color,fill='#7F00FF')
        elif self.tempMK<=140:
            self.subcanvas_boil.itemconfig(self.boil_water_color,fill='#FF00FF')
        elif self.tempMK<=160:
            self.subcanvas_boil.itemconfig(self.boil_water_color,fill='#FF007F')
        elif self.tempMK>=180:
            self.subcanvas_boil.itemconfig(self.boil_water_color,fill='#FF0000')

        #Update temperatures in stats box
        self.stat_tempMK.set('{:.1f}'.format(self.tempMK))
        self.stat_tempMH.set('{:.1f}'.format(self.tempMH))
        self.stat_tempBK.set('{:.1f}'.format(self.tempBK))

        #Update the duty cycle in the stats box, this has to be updated here since it can't be updated from a subprocess using the multiprocessing method
        self.stat_heatB_DC.set('{:.0f}'.format(self.data_array[9]))
        self.stat_heatM_DC.set('{:.0f}'.format(self.data_array[10]))
        
        #Update duty cycle optimization algorithm status
        if self.data_array[14]==1:
            self.stat_DCopt_act.set('ON',foreground="green")
        elif self.data_array[14]==0:
            self.stat_DCopt_act.set('OFF',foreground="red")

        t2=time.time()
        next_loop_time=int((1000/self.temp_freq)-(t2-t1)*1000)
        if next_loop_time<0:
            next_loop_time=0
        
        # Loop around again
        self.temp_loop=self.master.after(next_loop_time, self.read_all_temps)


    ## Function used to handle starting and stopping of multiprocessing process for mash and boil control using duty cycle optimization when necessary
    def heater_StartStop(self):
        if self.heatM_ON==1 or self.heatB_ON==1:
            self.heater_control_Proc_EXIT.value=0
            self.heater_control_proc=mp.Process(target=self.heater_control_process, args=(self.heater_control_Proc_EXIT,self.data_array))
            self.heater_control_proc.start()
        elif self.heatM_ON==0 and self.heatB_ON==0:
            self.heater_control_Proc_EXIT.value=1
            try:
                self.heater_control_proc.join()
            except:
                pass
        else:
            pass


    ## Heater control loop
    def heater_control_process(self,heater_control_Proc_EXIT,data_array):
        print('Heater control process started.')
        while heater_control_Proc_EXIT.value==0:
            #Calculate duty cycles for mash and boil heater
            #Mash
            if data_array[1]==1:
                data_array[10],data_array[12]=self.PI_ctrl(data_array[7],data_array[3],self.P_M,self.I_M,data_array[12]) #PI control to determine duty cycle
                t_on_M=(data_array[10]/100)*self.DCM_T #sec
                t_off_M=self.DCM_T-t_on_M; #sec
            else:
                t_on_M=0
            
            #Boil
            if data_array[2]==1:
                if data_array[6]==1:
                    data_array[9],data_array[13]=self.PI_ctrl(data_array[8],data_array[4],self.P_B,self.I_B,data_array[13]) #PI control to determine duty cycle
                elif data_array[6]==0:
                    pass
                t_on_B=(data_array[9]/100)*self.DCB_T #sec
                t_off_B=self.DCB_T-t_on_B; #sec
            else:
                t_on_B=0

# Figure out if the amount of time would cause the optimization algorithm to activate

### data_array[12] and [13] need to be reset when the control loop goes active for the first time or after a manual-to-auto switch


    ## Function used to handle starting and stopping of multiprocessing process for writing the log file
    def logging_StartStop(self):
        if self.log_ON==1:
            self.loggingProc_EXIT.value=0
            self.logging_proc=mp.Process(target=self.write_log_process, args=(self.loggingProc_EXIT,self.data_array))
            self.logging_proc.start()
        elif self.log_ON==0:
            self.loggingProc_EXIT.value=1
            self.logging_proc.join()

    #Multiprocessing process used to write to log file
    def write_log_process(self,loggingProc_EXIT,data_array):
        print('Data logging process started.')
        timestr = time.strftime("%Y%m%d-%H%M")
        self.log_file=open('PyBrau_Log_'+timestr+'.txt','w')
        self.log_file.write('PyBrau Data Log\n')
        self.log_file.write('%s\n\n' % timestr)
        self.log_file.write('Pump Mash_heater Boil_heater Mash_temp Boil_temp Mash_heater_temp Boil_type Mash_setpoint Boil_setpoint Boil_dutycycle Mash_dutycycle Mash_errorSum Boil_errorSum\n')
        tstart=time.time()
        while loggingProc_EXIT.value==0:
            tsamp=time.time()
            self.log_file.write('%.1f %d %d %d %.1f %.1f %.1f %d %.1f %.1f %d %d %.1f %.1f\n' % (tsamp-tstart,data_array[0],data_array[1],data_array[2],data_array[3],data_array[4],data_array[5],data_array[6],data_array[7],data_array[8],data_array[9],data_array[10],data_array[12],data_array[13]))
            time.sleep(1/data_array[11])
        self.log_file.close()
        print('Data logging process stopped.')


    ## Display debug data
    def debug_display(self):
        if self.debug==1:
            print('Comms = %d' % self.comms_status)
            print('Pump = %d' % self.pump_ON)
            print('Mash heater = %d' % self.heatM_ON)
            print('Boil heater = %d' % self.heatB_ON)
            print('Mash temp = %.1f' % self.tempMK)
            print('Boil temp = %.1f' % self.tempBK)
            print('Mash heater temp = %.1f' % self.tempMH)
            print('Boil type = %d' % self.boilMA)
            print('Mash setpoint input = %.1f' % self.setMK_IN)
            print('Mash setpoint = %.1f' % self.setMK)
            print('Boil setpoint input = %.1f' % self.setBK_IN)
            print('Boil setpoint = %.1f' % self.setBK)
            print('Boil duty cycle input = %d' % self.heatB_DC_IN)
            print('Boil duty cycle = %d' % self.heatB_DC)
            print('Mash duty cycle = %d' % self.heatM_DC)
            print('Data logging = %d' % self.log_ON)
            print('Duty cycle optimization = %d' % self.DCopt)
            print('Duty cycle weight mash input = %d' % self.setDC_MW_IN)
            print('Duty cycle weight boil input = %d' % (100-self.setDC_MW_IN))
            print('Duty cycle weight (M | B) = %.2f | %.2f\n' % (self.setDC_MW,self.setDC_BW))
        return None



if __name__ == "__main__":
    root = tk.Tk()
    BC = brew_control(root)
    root.resizable(width=tk.FALSE,height=tk.FALSE)
    root.mainloop()
