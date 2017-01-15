'''
    PyBrau.py
    
    Description: A Python TKINTER GUI for controlling the entire
                 hot side of the brewing processes from RIMS mashing
                 to boiling. GUI was designed to be used with an 
                 electric brew setup for both mashing and boiling.  
                 This verision is specifically designed for use on 
                 the offical Raspberry Pi touch screen.
    
    Revision History
    14 Jan 2017 - Created and debugged
    
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
    1. Complete system test
    
    '''


import tkinter as tk
import time
import sys
import math
#sys.path.append('/Users/lsoltmann/CodeProjects/DLP_IO8_G') #For MAC only
from DLP_IO8_G_py import DLP
from Thermistor_B57861S import thermistor


class brew_control:
    def __init__(self,master):
        self.master=master

        ##Create main window of size WxH
        w=800 #Designed to fit perfectly within the display range of the offically Raspberry Pi display
        h=412
        self.mainWindow = tk.Frame(self.master, width=w, height=h)
        self.master.title('Py Brau V1.0')
        self.mainWindow.pack()
        
        ##Debug
        self.debug=0; #1=ON, 0=OFF, outputs all state variables to screen after any button event
        
        ##System variables
        self.comms_status=0 #0,1 - indicates whether or not connected to USB DAQ
        self.pump_ON=0 #0,1 - indicates whether the pump is on or not
        self.heatM_ON=0 #0,1 - indicates whether the mash RIMS heating element is on or not, cannot be turned out without pump on
        self.heatB_ON=0 #0,1 - indicates whether the boil kettle heating element is on or not
        self.tempMK=0 #float - mash tun kettle temperature
        self.tempBK=0 #float - boil kettle temperature
        self.tempMH=0 #float - RIMS heater temperature
        self.boilMA=0 #0,1 - 0=manual control of boil element, 1=auto control of boil element
        self.setMK=0 #int - setpoint temperature for mash tun kettle
        self.setMK_IN=154 #Inital input for mash temperature
        self.setBK=0 #int - active setpoint temperature for boil kettle
        self.setBK_IN=170 #Inital input for boil temperature
        self.heatB_DC=0 #int - active duty cycle of boil heater
        self.heatB_DC_man=0 #int - manual duty cycle of boil heater
        self.heatB_DC_IN=0 #Inital input for boil duty cycle
        self.heatM_DC=0 #int - duty cycle of mash heater
        self.setDC_BW=0.5 #int - Duty cycle weight given to boil in optimization algorithm (0 <= x <= 1, 0.5 is equal weight between mash and boil)
        self.setDC_MW=0.5 #int - Duty cycle weight given to mash in optimization algorithm (0 <= x <= 1, 0.5 is equal weight between mash and boil)
        self.setDC_MW_IN=50 #Inital input for duty cycle optimization mash weight (divided by 100 when used in algorithm)
        self.setDC_BW_IN=50 #Inital input for duty cycle optimization boil weight (divided by 100 when used in algorithm)
        self.log_ON=0 #0,1 - data logging on or not
        self.DCopt=0 #0,1 - duty cycle optimization algorithm active or not
        
        ##Control variables
        self.DC_T=0.5 #Duty cycle period in seconds for heaters
        self.P_M=0.375 #Proportional gain - mash
        self.I_M=0.09375 #Integral gain - mash
        self.P_B=0.375 #Proportional gain - boil
        self.I_B=0.09375 #Integral gain - boil
        self.VREF=5.0 #Reference voltage used by thermistor
        self.THERM=thermistor()
        self.esum_M=0 #error summation used by integrator - mash
        self.esum_B=0 #error summation used by integrator - boil
        
        self.log_dt=1 #sec, time between data log writes *NOTE: must be <= DC_T
        self.gui_update_dt=0.75 #sec, time between GUI updates *NOTE: must be <= DC_T
        
        self.temp_filt_cutoff=3 #Hz, cutoff frequency for temperature filter
        self.temp_filt_coef=(2*math.pi*(1/self.DC_T)*self.temp_filt_cutoff)/(2*math.pi*(1/self.DC_T)*self.temp_filt_cutoff+1) #First order low pass filter for temperature readings
        self.first_time=1
        self.first_log=1

        ##Create all the windows
        self.init_daq_win()
        self.init_mash_win()
        self.init_boil_win()
        self.init_switch_win()
        self.init_mash_stats()
        self.init_boil_stats()
        self.init_cntrl_button_win()
        self.init_DCopt_stats()
        self.init_DCopt_ACT()
    
        ##Initialize switch panel in disabled mode since no device connection has been established
        self.pump_button.config(state = 'disabled')
        self.boil_button.config(state = 'disabled')
        self.boil_type_button.config(state = 'disabled')
        self.log_button.config(state = 'disabled')
        
        ##Check loop time compatibility
        if self.log_dt < self.DC_T:
            print('\n**** WARNING! Data log sampling time is less than heater control period. Setting log sampling time equal to heater control period. ****')
            self.log_dt=self.DC_T
        if self.gui_update_dt < self.DC_T:
            print('\n**** WARNING! GUI update time is less than heater control period. Setting GUI update time equal to heater control period. ****')
            self.gui_update_dt=self.DC_T
    
        ##FOR DEBUG ONLY
        self.debug_display()


    #################### USB DLP-IO8-G DAQ CONNECTION WINDOW AND BUTTON ####################
    def init_daq_win(self):
        ##Window location
        win_loc_x=20
        win_loc_y=20

        ##Create the subframe where the DAQ location and status are located
        subframe_daq = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)

        ##Connection status light
        daq_status_light_canvas = tk.Canvas(subframe_daq,width=15,height=15)
        daq_status_light = daq_status_light_canvas.create_oval(5, 5, 15, 15,fill="red")
        daq_status_light_canvas.pack(side=tk.LEFT,padx=(5,0))

        ##Connect button
        daq_connect_button = tk.Button(subframe_daq, text="Connect",command=lambda:self.connect_to_daq(daq_status_light_canvas,daq_status_light,daq_loc,daq_connect_button))
        daq_connect_button.pack(side=tk.LEFT,padx=(5,5), pady=10)


        ##Entry field for device location
        #daq_loc = tk.StringVar(subframe_daq, value="/dev/tty.usbserial-12345678") #Mac
        daq_loc = tk.StringVar(subframe_daq, value="/dev/ttyUSB0")
        #daq_loc = tk.StringVar(subframe_daq, value="test") #Makes testing easier
        daq_field = tk.Entry(subframe_daq, width=25, textvariable=daq_loc).pack(side=tk.RIGHT,padx=(0,5))


        subframe_daq.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='DEVICE').place(x=win_loc_x+20, y=win_loc_y,anchor=tk.W)

    def connect_to_daq(self,daq_status_light_canvas,daq_status_light,daq_loc,daq_connect_button):
        ##Open device if it wasn't previously open
        if self.comms_status==0:
            if (daq_loc.get() == "test"):
                daq_status_light_canvas.itemconfig(daq_status_light, fill="green")
                self.comms_status=1
                daq_connect_button.config(text="Disconnect")
                print('Test Mode!') #Can't do a whole lot in this mode. Mostly for testing buttons.
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
            
                #If open was not successfull, report error
                else:
                    daq_status_light_canvas.itemconfig(daq_status_light, fill="red")
                    self.comms_status=0
                    print('Device open error!')
        ##Close device
        else:
            try:
                #Cancel temp loop
                self.master.after_cancel(self.temp_loop)
                self.first_time=1
                #Set all outputs to zero
                self.DAQ.setDigitalOutput(4,0)
                self.DAQ.setDigitalOutput(5,0)
                self.DAQ.setDigitalOutput(6,0)
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
            self.t_lastGUIupdate=time.time()
            self.t_logUpdate=time.time()
            self.main_loop()
        elif self.comms_status==0:
            #If comms are closed, set all buttons to OFF and disable them
            self.pump_button.config(state = 'disabled')
            self.pump_button.config(text="PUMP      <OFF>  ON",justify=tk.LEFT)
            self.pump_ON=0
            self.subcanvas_mash.itemconfig(self.mash_pump_text, text='OFF',fill='black')
            self.subcanvas_mash.itemconfig(self.mash_pump_box,fill='white')
            self.stat_pump_ON.set('OFF')
            self.boil_button.config(state = 'disabled')
            self.boil_button.config(text="BOIL      <OFF>  ON",justify=tk.LEFT)
            self.heatB_ON=0
            self.boil_type_button.config(state = 'disabled')
            self.stat_heatB_ON.set('OFF')
            self.mash_button.config(state = 'disabled')
            self.mash_button.config(text="MASH      <OFF>  ON",justify=tk.LEFT)
            self.heatM_ON=0
            self.subcanvas_mash.itemconfig(self.mash_heater_color1,fill='white')
            self.stat_heatM_ON.set('OFF')
            self.heatB_DC=0
            self.heatB_DC_man=0
            self.stat_heatB_DC.set(self.heatB_DC)
            self.log_button.config(text="DATA LOG      <OFF>  ON",justify=tk.LEFT)
            self.log_button.config(state = 'disabled')
            self.log_ON=0
            self.esum_M=0
            self.esum_B=0
        
        ##FOR DEBUG ONLY
        self.debug_display()


    #################### SWITCH PANEL ####################
    def init_switch_win(self):
        ##Window location
        win_loc_x=450
        win_loc_y=20
        
        ##Create the subframe where the all the switches are
        subframe_switchPanel = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
    
        ##Mash ON/OFF button
        self.mash_button = tk.Button(subframe_switchPanel, text="MASH      <OFF>  ON",justify=tk.LEFT,wraplength=70,state = 'disabled',command=lambda:self.mash_command(self.mash_button))
        self.mash_button.grid(column = 0, row = 0, pady=10)
        ##PUMP ON/OFF button
        self.pump_button = tk.Button(subframe_switchPanel, text="PUMP      <OFF>  ON",justify=tk.LEFT,wraplength=70,command=lambda:self.pump_command(self.pump_button,self.mash_button))
        self.pump_button.grid(column = 1, row = 0, pady=10)
        ##BOIL ON/OFF button
        self.boil_button = tk.Button(subframe_switchPanel, text="BOIL      <OFF>  ON",justify=tk.LEFT,wraplength=70,command=lambda:self.boil_command(self.boil_button))
        self.boil_button.grid(column = 2, row = 0, pady=10)
        ##BOIL auto/manual button
        self.boil_type_button = tk.Button(subframe_switchPanel, text="BOIL CNTL         <MAN>  AUTO",justify=tk.LEFT,wraplength=100,command=lambda:self.boil_type_command(self.boil_type_button))
        self.boil_type_button.grid(column = 0, row = 1)
        ##Data Logging button
        self.log_button = tk.Button(subframe_switchPanel, text="DATA LOG      <OFF>  ON",justify=tk.LEFT,wraplength=70,command=lambda:self.log_command(self.log_button))
        self.log_button.grid(column = 1, row = 1)
    
        subframe_switchPanel.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='SWITCH PANEL').place(x=win_loc_x+20, y=win_loc_y,anchor=tk.W)

    
    ########### SWITCH PANEL FUNCTIONS ###########
    ##Master mash button
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
        
        ##FOR DEBUG ONLY
        self.debug_display()

    ##Master boil button
    def boil_command(self,boil_button):
        if self.heatB_ON==0:
            boil_button.config(text="BOIL       OFF  <ON>",justify=tk.LEFT)
            self.heatB_ON=1
            self.stat_heatB_ON.set('ON')
        elif self.heatB_ON==1:
            boil_button.config(text="BOIL      <OFF>  ON",justify=tk.LEFT)
            self.heatB_ON=0
            self.stat_heatB_ON.set('OFF')
            self.esum_B=0
        
        ##FOR DEBUG ONLY
        self.debug_display()

    ##Pump button
    def pump_command(self,pump_button,mash_button):
        if self.pump_ON==0: #State of variable when button was pressed
            pump_button.config(text="PUMP       OFF  <ON>",justify=tk.LEFT)
            self.pump_ON=1
            mash_button.config(state = 'active')
            self.stat_pump_ON.set('ON')
            self.subcanvas_mash.itemconfig(self.mash_pump_text, text='ON',fill='black')
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
            self.esum_M=0
        
        ##FOR DEBUG ONLY
        self.debug_display()

    ##Boil manual/auto button
    def boil_type_command(self,boil_type_button):
        if self.boilMA==0:
            boil_type_button.config(text="BOIL CNTL           MAN  <AUTO>",justify=tk.LEFT)
            self.boilMA=1
            self.stat_boilMA.set('AUTO')
            self.stat_heatB_DC.set('{:.0f}'.format(self.heatB_DC))
        elif self.boilMA==1:
            boil_type_button.config(text="BOIL CNTL          <MAN>  AUTO",justify=tk.LEFT)
            self.boilMA=0
            self.heatB_DC=self.heatB_DC_man
            self.stat_boilMA.set('MAN')

        #Reset integrator
        self.esum_B=0

        ##FOR DEBUG ONLY
        self.debug_display()
    
    ##Data logging button
    def log_command(self,log_button):
        if self.log_ON==0:
            log_button.config(text="DATA LOG      OFF  <ON>",justify=tk.LEFT)
            self.log_ON=1
        elif self.log_ON==1:
            log_button.config(text="DATA LOG      <OFF>  ON",justify=tk.LEFT)
            self.log_ON=0
        
        ##FOR DEBUG ONLY
        self.debug_display()

    #################### BUTTON PANEL FOR TEMP/DC CONTROL ####################
    def init_cntrl_button_win(self):
        ##Window location
        win_loc_x=13
        win_loc_y=320
        
        ##Create the subframe where the all the switches are
        self.subframe_buttonPanel = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        
        ##Mash Temp Label
        self.mash_button_label=tk.Label(self.subframe_buttonPanel, text='MASH')
        self.mash_button_label.grid(row=0,column=0,columnspan=2,pady=(5,0))
        ##Mash Temp +10 button
        self.mash_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_p10())
        self.mash_p10_button.grid(column = 0, row = 1,padx=(5,0))
        ##Mash Temp -10 button
        self.mash_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_m10())
        self.mash_m10_button.grid(column = 0, row = 2,padx=(5,0))
        ##Mash Temp +1 button
        self.mash_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_p1())
        self.mash_p1_button.grid(column = 1, row = 1)
        ##Mash Temp -1 button
        self.mash_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_mash_setpoint_m1())
        self.mash_m1_button.grid(column = 1, row = 2)
        
        ##Boil Temp Label
        self.boil_button_label=tk.Label(self.subframe_buttonPanel, text='BOIL')
        self.boil_button_label.grid(row=0,column=2,columnspan=2,pady=(5,0))
        ##Boil Temp +10 button
        self.boil_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_p10())
        self.boil_p10_button.grid(column = 2, row = 1,padx=(5,0))
        ##Boil Temp -10 button
        self.boil_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_m10())
        self.boil_m10_button.grid(column = 2, row = 2,padx=(5,0))
        ##Boil Temp +1 button
        self.boil_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_p1())
        self.boil_p1_button.grid(column = 3, row = 1)
        ##Boil Temp -1 button
        self.boil_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_boil_setpoint_m1())
        self.boil_m1_button.grid(column = 3, row = 2)
        
        ##DC Temp Label
        self.dc_button_label=tk.Label(self.subframe_buttonPanel, text='DC')
        self.dc_button_label.grid(row=0,column=4,columnspan=2,pady=(5,0))
        ##DC +10 button
        self.dc_p10_button = tk.Button(self.subframe_buttonPanel, text="+10",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_p10())
        self.dc_p10_button.grid(column = 4, row = 1, padx=(5,0))
        ##DC -10 button
        self.dc_m10_button = tk.Button(self.subframe_buttonPanel, text="-10",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_m10())
        self.dc_m10_button.grid(column = 4, row = 2, padx=(5,0))
        ##DC +1 button
        self.dc_p1_button = tk.Button(self.subframe_buttonPanel, text="+1",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_p1())
        self.dc_p1_button.grid(column = 5, row = 1)
        ##DC -1 button
        self.dc_m1_button = tk.Button(self.subframe_buttonPanel, text="-1",justify=tk.LEFT,command=lambda:self.input_DC_setpoint_m1())
        self.dc_m1_button.grid(column = 5, row = 2)
        
        ##Weighting critiera for duty cycle control optimization
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
        
        ##Set all inputs button
        self.set_inputs_button = tk.Button(self.subframe_buttonPanel, text="SET   ",justify=tk.CENTER,wraplength=30,command=lambda:self.set_all_inputs_cmd())
        self.set_inputs_button.grid(column = 8, row=1,rowspan=2,sticky=tk.N+tk.S,pady=(2,0),padx=(5,5))
        
        self.subframe_buttonPanel.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='CONTROL PANEL').place(x=win_loc_x+20, y=win_loc_y,anchor=tk.W)
    
    #################### BUTTON PANEL FUNCTIONS ####################
    ##Boil
    def input_boil_setpoint_p10(self):
        # Increase boil temperature by 10degF and limit to 212
        self.setBK_IN=self.setBK_IN+10
        if self.setBK_IN>=212:
            self.setBK_IN=212
        self.stat_inBK.set(self.setBK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()
    
    def input_boil_setpoint_m10(self):
        # Decrease boil temperature by 10degF and limit to 70
        self.setBK_IN=self.setBK_IN-10
        if self.setBK_IN<=70:
            self.setBK_IN=70
        self.stat_inBK.set(self.setBK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    def input_boil_setpoint_p1(self):
        # Increase boil temperature by 1degF and limit to 212
        self.setBK_IN=self.setBK_IN+1
        if self.setBK_IN>=212:
            self.setBK_IN=212
        self.stat_inBK.set(self.setBK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()
    
    def input_boil_setpoint_m1(self):
        # Decrease boil temperature by 1degF and limit to 70
        self.setBK_IN=self.setBK_IN-1
        if self.setBK_IN<=70:
            self.setBK_IN=70
        self.stat_inBK.set(self.setBK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    ##Duty Cycle
    def input_DC_setpoint_p10(self):
        # Increase boil duty cycle by 10% and limit to 100
        self.heatB_DC_IN=self.heatB_DC_IN+10
        if self.heatB_DC_IN>=100:
            self.heatB_DC_IN=100
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ##FOR DEBUG ONLY
        self.debug_display()
    
    def input_DC_setpoint_m10(self):
        # Decrease boil duty cycle by 10% and limit to 0
        self.heatB_DC_IN=self.heatB_DC_IN-10
        if self.heatB_DC_IN<=0:
            self.heatB_DC_IN=0
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    def input_DC_setpoint_p1(self):
        # Increase boil duty cycle by 1% and limit to 100
        self.heatB_DC_IN=self.heatB_DC_IN+1
        if self.heatB_DC_IN>=100:
            self.heatB_DC_IN=100
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ##FOR DEBUG ONLY
        self.debug_display()
    
    def input_DC_setpoint_m1(self):
        # Decrease boil duty cycle by 1% and limit to 0
        self.heatB_DC_IN=self.heatB_DC_IN-1
        if self.heatB_DC_IN<=0:
            self.heatB_DC_IN=0
        self.stat_inheatB_DC.set(self.heatB_DC_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    #Mash
    def input_mash_setpoint_p10(self):
        # Increase mash temperature by 10degF and limit to 180
        self.setMK_IN=self.setMK_IN+10
        if self.setMK_IN>=180:
            self.setMK_IN=180
        self.stat_inMK.set(self.setMK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()
    
    def input_mash_setpoint_m10(self):
        # Decrease mash temperature by 10degF and limit to 70
        self.setMK_IN=self.setMK_IN-10
        if self.setMK_IN<=70:
            self.setMK_IN=70
        self.stat_inMK.set(self.setMK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    def input_mash_setpoint_p1(self):
        # Increase mash temperature by 1degF and limit to 180
        self.setMK_IN=self.setMK_IN+1
        if self.setMK_IN>=180:
            self.setMK_IN=180
        self.stat_inMK.set(self.setMK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()
    
    def input_mash_setpoint_m1(self):
        # Decrease mash temperature by 1degF and limit to 70
        self.setMK_IN=self.setMK_IN-1
        if self.setMK_IN<=70:
            self.setMK_IN=70
        self.stat_inMK.set(self.setMK_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    #DC Weight
    def input_DC_W_p10(self):
        # Increase duty cycle optimization mash weight by 10% and limit to 99%
        self.setDC_MW_IN=self.setDC_MW_IN+10
        if self.setDC_MW_IN>=99:
            self.setDC_MW_IN=99
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    def input_DC_W_m10(self):
        # Decrease duty cycle optimization mash weight by 10% and limit to 1%
        self.setDC_MW_IN=self.setDC_MW_IN-10
        if self.setDC_MW_IN<=1:
            self.setDC_MW_IN=1
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    def input_DC_W_p1(self):
        # Increase duty cycle optimization mash weight by 1% and limit to 99%
        self.setDC_MW_IN=self.setDC_MW_IN+1
        if self.setDC_MW_IN>=99:
            self.setDC_MW_IN=99
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    def input_DC_W_m1(self):
        # Decrease duty cycle optimization mash weight by 1% and limit to 1%
        self.setDC_MW_IN=self.setDC_MW_IN-1
        if self.setDC_MW_IN<=1:
            self.setDC_MW_IN=1
        self.stat_inDCMW.set(self.setDC_MW_IN)
        self.stat_inDCBW.set(100-self.setDC_MW_IN)
        ##FOR DEBUG ONLY
        self.debug_display()

    ##Set all inputs
    def set_all_inputs_cmd(self):
        # Set variables
        self.setMK=self.setMK_IN
        self.setBK=self.setBK_IN
        self.heatB_DC_man=self.heatB_DC_IN
        self.setDC_MW=self.setDC_MW_IN/100
        self.setDC_BW=(100-self.setDC_MW_IN)/100
        
        # Update the gui
        self.stat_setMK.set(self.setMK)
        self.stat_setBK.set(self.setBK)
        self.stat_heatB_DC_man.set(self.heatB_DC_man)
        self.stat_setDCMW.set(self.setDC_MW_IN)
        self.stat_setDCBW.set(100-self.setDC_MW_IN)
        
        ##FOR DEBUG ONLY
        self.debug_display()


    #################### MASH WINDOW ####################
    def init_mash_win(self):
        ##Window location
        win_loc_x=10
        win_loc_y=95
        Kshift=80
        WK=150
        HK=150
        BW=6 #simulated border width
        FC=1
        
        ##Create the subframe where all mash related items go
        self.subframe_mash = tk.Frame(self.master, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        #Create canvas for mash graphics
        self.subcanvas_mash=tk.Canvas(self.subframe_mash,width=270,height=215)
        
        ##Place the mash canvas
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
        ##Window location
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
        ##Window location
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
        
        ##Create the subframe where all boil related items go
        self.subframe_boil = tk.Frame(self.master, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        ##Create canvas for boil graphics
        self.subcanvas_boil=tk.Canvas(self.subframe_boil)
        ##Place the boil canvas
        self.subframe_boil.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='BOIL').place(x=win_loc_x+(WK/2), y=win_loc_y-10,anchor=tk.CENTER)
        
        ##Draw simulated boil kettle
        self.subcanvas_boil.create_rectangle(0,0,WK,HK,outline='black',width=0,fill='black') #simulated border
        self.subcanvas_boil.create_rectangle(0+BW1+3,0+BW1+3,WK-BW1*FC,(HK-2*BW1)/3+BW1,outline='black',width=0,fill='#ececec') #simulated air
        self.boil_water_color=self.subcanvas_boil.create_rectangle(0+BW1+3,(HK-2*BW1)/3+BW1,WK-BW1*FC,HK-BW1*FC,outline='black',width=0,fill='blue') #simulated water
        self.boil_tolerance=self.subcanvas_boil.create_rectangle(WK/2-W1/2+x1+BW1,(((HK-2*BW)/3)/2)+BW-H1/3,WK/2-W1/2+x2-BW1,(((HK-2*BW)/3)/2)+BW+H1/3,outline='black',width=0,fill='red') #temperature tolerance indicator box
        self.boil_temp_color=self.subcanvas_boil.create_text(self.boil_kettle_loc_x,self.boil_kettle_loc_y,text=self.tempBK,fill='black',anchor=tk.CENTER)
        self.subcanvas_boil.pack()


    #################### BOIL STATS ####################
    def init_boil_stats(self):
        ##Window location
        win_loc_x=605
        win_loc_y=150
        
        self.subframe_boil_stats = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        tk.Label(self.subframe_boil_stats, text="Setpoint-IN:",foreground="blue").grid(row=0,column=0,padx=(5,5),pady=(5,0),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Setpoint-ACT:").grid(row=1,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Boil Temp:").grid(row=2,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Control Mode:").grid(row=3,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater Status:").grid(row=4,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater DC-IN:",foreground="blue").grid(row=5,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater DC-MAN:").grid(row=6,column=0,padx=(5,5),sticky=tk.E)
        tk.Label(self.subframe_boil_stats, text="Heater DC-ACT:").grid(row=7,column=0,padx=(5,5),sticky=tk.E)
        
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
        
        self.stat_heatB_DC_man=tk.StringVar(self.subframe_boil_stats,value=self.heatB_DC_man)
        self.boil_stat_heatDC_man_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_heatB_DC_man)
        self.boil_stat_heatDC_man_label.grid(row=6,column=1)
        
        self.stat_heatB_DC=tk.StringVar(self.subframe_boil_stats,value=self.heatB_DC)
        self.boil_stat_heatDC_label=tk.Label(self.subframe_boil_stats, textvariable=self.stat_heatB_DC)
        self.boil_stat_heatDC_label.grid(row=7,column=1)
        
        self.subframe_boil_stats.place(x=win_loc_x, y=win_loc_y)
        tk.Label(self.master, text='BOIL STATS').place(x=win_loc_x+35, y=win_loc_y,anchor=tk.W)
    
    
    #################### DC OPTIMIZATION STATS ####################
    def init_DCopt_stats(self):
        ##Window location
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
        ##Window location
        win_loc_x=210
        win_loc_y=260
        
        self.subframe_DCopt_act = tk.Frame(self.master, relief=tk.GROOVE, borderwidth=2)
        tk.Label(self.subframe_DCopt_act, text="DC Optimization:").grid(row=0,column=0,padx=(10,0),pady=(10,10))
    
        self.stat_DCopt_act=tk.StringVar(self.subframe_DCopt_act,value='OFF')
        self.stat_DCopt_act_label=tk.Label(self.subframe_DCopt_act, textvariable=self.stat_DCopt_act,foreground='green')
        self.stat_DCopt_act_label.grid(row=0,column=1,padx=(0,10),pady=(10,10))
    
        self.subframe_DCopt_act.place(x=win_loc_x, y=win_loc_y)


################################################ CONTROL/FLOW FUNCTIONS ###############################################
    ##PI control to determine duty cycle for both mash and boil controls
    def PI_ctrl(self,SP,PV,kp,ki,esum):
        #SP=setpoint
        #PV=process variable
        #kp=proportional gain
        #ki=integral gain
        #esum=error sum
        
        ##Calculate duty cycle for heater
        error=SP-PV
        esum=esum+(error*self.DC_T)
        #Limit the integrator to prevent windup
        if esum>5.0:
            esum=5.0
        elif esum<-5.0:
            esum=-5.0
        P=kp*error
        I=ki*esum
        u=P+I
        #Limit output to between 0 and 1
        if u>1.0:
            u=1.0
        elif u<0.0:
            u=0.0
        u=u*100 #Bring the duty cycle back to a value between 0 and 100.  This is only done for the dispaly and logging purpose.  The PID gains were orignially used with a 0 to 1 output so the that part of the algorithm will not be changed and just the final duty cycle brough up by two orders of magnitude.
        return u,esum
    
    ##Function to read all thermistors
    def read_temps(self):
        #Read temperatures
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
        
        #Apply exponential moving average filter to temperature data
        self.tempMK=self.temp_filt_coef*tempMK_raw+(1-self.temp_filt_coef)*self.tempMK
        self.tempMH=self.temp_filt_coef*tempMH_raw+(1-self.temp_filt_coef)*self.tempMH
        self.tempBK=self.temp_filt_coef*tempBK_raw+(1-self.temp_filt_coef)*self.tempBK

    ##Function to control heaters
    def heater_control(self):
        ##Calculate raw duty cycles for mash and boil heater
        #Mash
        if self.heatM_ON==1:
            temp_heatM_DC,self.esum_M=self.PI_ctrl(self.setMK,self.tempMK,self.P_M,self.I_M,self.esum_M) #PI control to determine duty cycle
            u_M=temp_heatM_DC/100
        else:
            u_M=0
        
        #Boil
        if self.heatB_ON==1:
            if self.boilMA==1:
                temp_heatB_DC,self.esum_B=self.PI_ctrl(self.setBK,self.tempBK,self.P_B,self.I_B,self.esum_B) #PI control to determine duty cycle
                u_B=temp_heatB_DC/100
            elif self.boilMA==0:
                u_B=self.heatB_DC_man/100
        else:
            u_B=0

        ##Apply duty cycle optimization algorithm, if needed
        #
        #Algorithm is based on the cost function:
        #    cost=wB*[uB-uB_O]^2+wM*[uM-uM_O]^2
        #where  wB=weight applied to boil duty cycle input
        #       wM=weight applied to mash duty cycle input
        #       uB=raw boil duty cycle
        #       uM=raw mash duty cycle
        #       uB_O=optimized boil duty cycle
        #       uM_O=optimized mash duty cycle
        #
        #Constraints are:
        #    wB+wM=1
        #    uB_O+uM_O=1
        #
        if (u_B+u_M)>1:
            self.DCopt=1
            u_B=self.setDC_MW*(1-u_M)+self.setDC_BW*u_B
            u_M=1-u_B
        else:
            self.DCopt=0

        ##Record actual duty cycle for display
        self.heatB_DC=u_B*100
        self.heatM_DC=u_M*100

        ##Calculate time based on duty cycle
        t_on_M=u_M*self.DC_T #sec
        t_off_M=self.DC_T-t_on_M; #sec
        t_on_B=u_B*self.DC_T #sec
        t_off_B=self.DC_T-t_on_B; #sec
        delta_t=abs(t_on_M-t_on_B)
        
        ##Turn ON and OFF heaters
        #
        #[ 0 < x,y < 1]
        #
        #Case 1 (u_M=1,u_B=0)
        if (u_M==1 and u_B==0):
            self.DAQ.setDigitalOutput(6,0)
            self.DAQ.setDigitalOutput(5,1)
            time.sleep(self.DC_T)
        
        #Case 2 (u_M=0,u_B=1)
        elif (u_M==0 and u_B==1):
            self.DAQ.setDigitalOutput(5,0)
            self.DAQ.setDigitalOutput(6,1)
            time.sleep(self.DC_T)
        
        #Case 3 (u_M=0,u_B=0)
        elif (u_M==0 and u_B==0):
            self.DAQ.setDigitalOutput(5,0)
            self.DAQ.setDigitalOutput(6,0)
            time.sleep(self.DC_T)
        
        #Case 4 (u_M=x,u_B=0)
        elif (u_B==0):
            self.DAQ.setDigitalOutput(6,0)
            self.DAQ.setDigitalOutput(5,1)
            time.sleep(t_on_M)
            self.DAQ.setDigitalOutput(5,0)
            time.sleep(t_off_M)
        
        #Case 5 (u_M=0,u_B=y)
        elif (u_M==0):
            self.DAQ.setDigitalOutput(5,0)
            self.DAQ.setDigitalOutput(6,1)
            time.sleep(t_on_B)
            self.DAQ.setDigitalOutput(6,0)
            time.sleep(t_off_B)
        
        #Case 6 (u_M=x,u_B=y, x+y=1)
        elif (u_M+u_B==1):
            self.DAQ.setDigitalOutput(6,0)
            self.DAQ.setDigitalOutput(5,1)
            time.sleep(t_on_M)
            self.DAQ.setDigitalOutput(5,0)
            self.DAQ.setDigitalOutput(6,1)
            time.sleep(t_off_M)

        #Case 7 (u_M=x,u_B=y, x+y<1)
        elif (u_M+u_B<1):
            self.DAQ.setDigitalOutput(6,0)
            self.DAQ.setDigitalOutput(5,1)
            time.sleep(t_on_M)
            self.DAQ.setDigitalOutput(5,0)
            time.sleep(delta_t)
            self.DAQ.setDigitalOutput(6,1)
            time.sleep(t_on_B)
        

    ##Function to update all temperature labels
    def update_gui(self):
        self.subcanvas_mash.delete(self.mash_heater_color2) # Update the mash heater temp in mash canvas
        self.mash_heater_color2=self.subcanvas_mash.create_text(self.mash_heater_loc_x,self.mash_heater_loc_y,text='{:.1f}'.format(self.tempMH),fill='black',anchor=tk.CENTER)

        self.subcanvas_mash.delete(self.mash_temp_color) # Update the mash kettle temp in mash canvas
        self.mash_temp_color=self.subcanvas_mash.create_text(self.mash_tun_loc_x,self.mash_tun_loc_y,text='{:.1f}'.format(self.tempMK),fill='black',anchor=tk.CENTER)
        
        ##Tolerance box color of mash kettle
        # +/-0.5deg = green, +/-0.5 to +/-1deg = yellow, >+/-1deg = red
        if abs(self.tempMK-self.setMK)>1:
            self.subcanvas_mash.itemconfig(self.mash_tolerance,fill='red')
        elif abs(self.tempMK-self.setMK)>0.5 and abs(self.tempMK-self.setMK)<=1:
            self.subcanvas_mash.itemconfig(self.mash_tolerance,fill='yellow')
        else:
            self.subcanvas_mash.itemconfig(self.mash_tolerance,fill='green')
        
        ##Change the mash kettle water color based on temperature
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
        
        ##Tolerance box color of boil kettle
        # +/-0.5deg = green, +/-0.5 to +/-1deg = yellow, >+/-1deg = red
        if abs(self.tempBK-self.setBK)>1:
            self.subcanvas_boil.itemconfig(self.boil_tolerance,fill='red')
        elif abs(self.tempBK-self.setBK)>0.5 and abs(self.tempBK-self.setBK)<=1:
            self.subcanvas_boil.itemconfig(self.boil_tolerance,fill='yellow')
        else:
            self.subcanvas_boil.itemconfig(self.boil_tolerance,fill='green')

        ##Change the boil kettle water color based on temperature
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

        ##Update temperatures in stats box
        self.stat_tempMK.set('{:.1f}'.format(self.tempMK))
        self.stat_tempMH.set('{:.1f}'.format(self.tempMH))
        self.stat_tempBK.set('{:.1f}'.format(self.tempBK))

        ##Update the duty cycle in the stats box
        self.stat_heatB_DC.set('{:.0f}'.format(self.heatB_DC))
        self.stat_heatM_DC.set('{:.0f}'.format(self.heatM_DC))
        
        ##Update duty cycle optimization algorithm status
        if self.DCopt==1:
            self.stat_DCopt_act.set('ON')
            self.stat_DCopt_act_label.config(foreground='#FFA500')
        elif self.DCopt==0:
            self.stat_DCopt_act.set('OFF')
            self.stat_DCopt_act_label.config(foreground='green')


    ##Function to write to data log
    def write_log(self):
        if self.log_ON==1:
            if self.first_log==1:
                timestr = time.strftime("%Y%m%d-%H%M")
                self.log_file=open('PyBrau_Log_'+timestr+'.txt','w')
                self.log_file.write('PyBrau Data Log\n')
                self.log_file.write('%s\n\n' % timestr)
                self.log_file.write('Time(sec) Pump Mash_heater Boil_heater Mash_temp(F) Boil_temp(F) Mash_heater_temp(F) Boil_type Mash_setpoint(F) Boil_setpoint(F) Boil_dutycycle_manual(%) Boil_dutycycle_active(%) Mash_dutycycle_active(%) Mash_errorSum Boil_errorSum DC_opt\n')
                self.tstart=time.time()
                self.first_log=0
            else:
                tsamp=time.time()
                self.log_file.write('%.1f %d %d %d %.1f %.1f %.1f %d %.1f %.1f %d %d %.1f %.1f\n' % (tsamp-self.tstart,self.pump_ON,self.heatM_ON,self.heatB_ON,self.tempMK,self.tempBK,self.tempMH,self.boilMA,self.setMK,self.setBK,self.heatB_DC_man,self.heatB_DC,self.heatM_DC,self.esum_M,self.esum_B,self.DCopt))
        if self.log_ON==0:
            try:
                self.log_file.close()
                self.first_log=1
            except:
                pass


    ########## Main loop for GUI ##########
    def main_loop(self):
        self.read_temps() #Read all temp sensors
        self.heater_control() #Turn on/off heaters based on input
        if ((time.time()-self.t_lastGUIupdate)>=self.gui_update_dt) or self.first_time==1:
            self.update_gui() #Update the GUI
            self.t_lastGUIupdate=time.time()
        if ((time.time()-self.t_logUpdate)>=self.log_dt) or self.first_time==1:
            self.write_log() #Write to data log
            self.t_logUpdate=time.time()
        #Loop around again
        self.first_time=0
        self.temp_loop=self.master.after(10, self.main_loop)


    ##Display debug data
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
