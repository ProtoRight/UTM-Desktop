/*
To be added/changed:
 - 
 -  



*/


/*

V7 - Microstepping now set as variable "microStep" and applied to all instances where steps need to be calculated. Should we do this for all similar variables (gear decuction, screw pitch, etc?)
V8 - Adding a linearity mode where you can see raw adc values from HX711 for checking against a known load cell. Increased idle sample duration for now from 500 to 1000
V9 - Added LOADCAL state that allows calibation of the loadcell while keeping manual control enabled, this allows the machine itself to generate require claibration load. Note; still requires external loadcell to check current load for cal
   - also added protections for Tare function. 
V11 - has correct calbration values for ATO 500KG loadcell. Adding individual Tensions and 3pt bend tests and calls. 
V13 - Add serial control for testing variables


*/


//Libraries
  #include <Wire.h>
  #include "HX711.h"
  #include "AccelStepper.h"
  #include "Pushbutton.h"

// DRO I2C address
  #define DRO_ADDR 0x10


//DRO Pins - moved over to NANO
 // #define DRO_CLK_PIN 4
 // #define DRO_DATA_PIN 5

//HX711 Pins
  #define HX711_CLK_PIN 6 // reversed pins 6 and 7 to account for perfboard soldering
  #define HX711_DATA_PIN 7

//Stepper Driver Pins
  #define DIR 8
  #define STEP 9
  #define ENABLE 10


//Define Buttons via pushbutton library
  Pushbutton MotorEnable_bt(3); //Motor Enable
  Pushbutton MotorUP_bt(11); // jog motor up
  Pushbutton MotorDWN_bt(12); // jog motor down


  HX711 scale; //declare scale
  //AccelStepper stepper(AccelStepper::DRIVER, STEP, DIR); // Declare Stepper to accelstepper library

// =====================
// TIMER1 STEPPING (NEW)
// =====================
  volatile bool stepEnabled = false;
  volatile bool stepState   = false;
  volatile uint16_t timerPeriodTicks = 3000; // default

// Timer1 clock = 16 MHz / 8 = 2 MHz
  uint16_t speedToTimerTicks(float stepsPerSec) {
    if (stepsPerSec <= 0) return 65535;
    return (uint16_t)(2000000.0 / stepsPerSec);
  }

  void setupTimer1() {
    noInterrupts();

    TCCR1A = 0;
    TCCR1B = 0;
    TCNT1  = 0;

    // CTC mode
    TCCR1B |= (1 << WGM12); //automatically clears Timer1 when we meet the comparison criteria

    // Prescaler = 8
    TCCR1B |= (1 << CS11); //dividing the true pulse count since we'd overrun the 62K pulses we could otherwise count

    OCR1A = timerPeriodTicks;
    TIMSK1 |= (1 << OCIE1A);

    interrupts();
  }

  ISR(TIMER1_COMPA_vect) {
    if (!stepEnabled) return;

    PINB = _BV(PB1);  // toggle STEP pin (pin 9) in 1 CPU cycle;
  }

// Global Variables

  //timing variables
    unsigned long testingSampleInterval = 50; // ms - minimum gap between RUNNING serial packets (SAMPLERATE command)
    unsigned long lastTestingSampleTime = 0;
    const unsigned long idleSampleInterval = 1000; // ms - Sample rate when machine is idle
    unsigned long lastIdleSampleTime = 0;

  // Load averaging between DRO ticks (Option 2)
    float loadAccum   = 0.0f;
    int   loadCount   = 0;
    float lastSentDRO = -9999.0f; // sentinel — ensures first point is always emitted
   

  // Other Variables 
   
    float CurrentDRO = 0.0;
    //float DRO_ZeroOffset = 0; // sets zero point for dro. DEPRECATED: now handled by Nano
    float CurrentLoad = 0.0;
     

  // motor speed variables 
    float actualJogSpeed = 50; // mm/min of actual crosshead movement - motor jog speed while machine is manually jogged. Motors have max rpm of 200. for 10:1 and 2mm pitch, top speed is 40mm/min. Seems consistent up to ~500 Assuming 1/4 microstepping
    float jogMax = 150; // maximum allowed jog speed, after this vlaue it becomes inconsistent
    float actualTestSpeed = 10; // mm/min of actual crosshead movement - motor jog speed while machine is in test THIS NUMBER IS A PLACEHOLDER

    /*
    
    ***UPDATED NOTE***
    After chanign how we're doing stepper commands, we are less concerned about these limitations. At slower stesting speeds we did see juttering with no microstepping, so now we are implemnting some microsteping. 

    NOTE: There are practical limitations to how quickly you can command the motor to move. 
    Using a 10:1 gear already means a more demanding amount of pulses/second, before we add any microstepping. 
    Using full 1/16 microstepping will be too demanding for many speed ranges of the crosshead. 
    It is recommended to use a microstepping value of 1/4 or coarser as a good compormise between speed and accuracy.
    Even without microstepping, a 1.8deg stepper, 10:1 gear reduction, and a 2mm pitch single start screw, a single step pulse results in (1*2)/(200*10)mm of crosshead movement, or 1 micron of movement
    1/1 uStepping = 0.001mm
    1/2 uStepping = 0.0005mm
    1/4 uStepping = 0.00025mm 

    */

    // EQUATION ((actualJogSpeed/Picth of Screw)*gear ratio*full steps per revolution*microstepping)/60 seconds
    float microStep = 4; // microstepping setting. for 1/4, you'd use 4
    float jog_StepSpeed = ((actualJogSpeed/2)*10*200*microStep)/60; //stepper velocity converted to microsteps per second to be used by accell stepper library commands. THIS NEEDS TO BE IDENTICAL TO WHAT IS IN THE CHANGE JOGSPEED SERIAL COMMAND
    float test_StepSpeed = ((actualTestSpeed/2)*10*200*microStep)/60;

  // SAFETY-RELATED
    int travelLimit = 40; //distance in mm that the test will stop at
    int loadLimit = 300; //safety load limit for DRO reading in KGs. anything at or over this will halt the test. New ATO loadcell rated for 500KG
    bool DriverEnableState = 1; //stores current state of the driver enable pin, high is off, low is on. can use the following structure to read from a momentary button and toggle the state

    //Safety Triggers
    volatile bool estopTriggered = false;


  //State Machine Setup
    enum SystemState { IDLE, RUNNING_3PT, RUNNING_T, FINISHED, ESTOP, RAWOUTPUT, LOADCAL }; //creating a new data type called "SystemState" that can have the following values: "IDLE, RUNNING, FINISHED"
    SystemState currentState = IDLE;    //creating new variable "currentState" of the type "SystemState" and setting default behavior to be IDLE
    SystemState previousState = IDLE;   //creating new variable "PreviousState" of the type "SystemState" and setting default behavior to be IDLE. Used for checking transitions between states

    // Seaprate state machine needed for hx711 loadcell cal routine
    enum CalState { CAL_IDLE, CAL_ZERO_WAIT, CAL_ZERO_DONE, CAL_WEIGHT_WAIT, CAL_DONE };
    CalState calState = CAL_IDLE;
    //loadcal variables
      long newOffset = 0;
      float newScale = 0.0;
      float calWeight = 0.0;



  // Serial text Input Handling
     String lastTextInput = ""; 



void setup() {
  // Pin Modes
    Serial.begin(250000);
    //pinMode(DRO_CLK_PIN, INPUT); MOVED TO NANO
    //pinMode(DRO_DATA_PIN, INPUT);MOVED TO NANO
    pinMode(DIR, OUTPUT);
    pinMode(STEP, OUTPUT);
    pinMode(ENABLE, OUTPUT);

  //HX711 PRE-DEFINES PINMODES
  //Pushbutton Also predefined Pin Modes

  //Interrup Pins
    pinMode(2, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(2),ESTOP_ISR,FALLING); //Calls function ESTOP_ISR whenever the button is pressed


  //Loadcell Setup
  //define loadcell constants 
    scale.begin(HX711_DATA_PIN, HX711_CLK_PIN);
    scale.set_gain(128);
    scale.set_offset(-7931); //calibrated with ATO loadcell on 5/3/26 with no attachments
    scale.set_scale(8797.361328); //calibrated at 200kg with ATO loadcell on 5/3/26
    scale.tare();

    digitalWrite(ENABLE, DriverEnableState); //starts with steppers disabled so you can manually adjust leadscrews for alignment if needed
  
  // overwrites serials default behavour of waiting a full second before timing out
    Serial.setTimeout(10); // 10 ms timeout
    Serial.println("BOOT OK");

    Wire.begin(); // I2C master

    setupTimer1();

}

void loop() {
 //unsigned long t = micros(); // timer for checking loop execution - also uncomment at end of loop
  lastTextInput = ""; //clears serial
  readDROFromNano(); // Read DRO over i2c  

  if(currentState != RAWOUTPUT){
    CurrentLoad = scale.get_units(1); //Read Loadcell 
  }

  //check for e-stop condition
  if(estopTriggered == true){
    estopTriggered = false;
    DriverEnableState = 1; 
    digitalWrite(ENABLE, 1);
    stepEnabled = false;
    currentState = ESTOP;
    Serial.println("ESTOP PRESSED - ALL MOTORS DISABLED");

    }
     
  // Read from Serial and parse input
  ReadSerialInput();

  // STATE MACHINE
  switch(currentState) {
    case IDLE:
      updateIdle();
      break;

    case RUNNING_3PT:
      updateRunning_3PT();
      break;

    case RUNNING_T:
      updateRunning_T();
      break;

    case FINISHED:
      DriverEnableState = 1;
      digitalWrite(ENABLE, DriverEnableState);
      //also display max load maybe?
      previousState = FINISHED;
      break;

    case RAWOUTPUT:
      updateRawOutput();
      break;

    case LOADCAL:
      updateLoadCal();
      break;

    case ESTOP:
      updateEStop();
      break;
  }

  // timer for checking loop execution - also uncomment at start of loop
    /*
    unsigned long loopTime = micros() - t;
    Serial.println(loopTime); // loop execution time in microseconds
    */

}


void readDROFromNano() {
  bool wasStepping = stepEnabled;
  stepEnabled = false;      // pause stepping ISR
  Wire.requestFrom(DRO_ADDR, 4); // 4 bytes float
  if(Wire.available() == 4) {
    float droVal;
    Wire.readBytes((char*)&droVal, 4);
    CurrentDRO = droVal;
  }
  stepEnabled = wasStepping; // resume stepping
}



void ReadSerialInput(){

if (Serial.available() > 0){ // If there is any data in serial buffer
  lastTextInput = Serial.readStringUntil('\n'); //read all characters until the new line signal in the buffer and put them into this string variable 
  lastTextInput.trim(); // Removes carriage return "\r" as well as any spaces
  lastTextInput.toUpperCase(); // converts everthing to uppercase
  if (lastTextInput == "IDLE"){
    currentState = IDLE;
    Serial.println("IDLE");
  } else if (lastTextInput == "RUN_3PT"){
      currentState = RUNNING_3PT;
      //DRO_ZeroOffset = CurrentDRO; // zero DRO at test start DEPRECATED: HANDLED BY NANO
      Serial.println("3 POINT BEND TEST STARTING");
  } else if (lastTextInput == "RUN_T"){
      currentState = RUNNING_T;
      //DRO_ZeroOffset = CurrentDRO; // zero DRO at test start DEPRECATED: HANDLED BY NANO
      Serial.println("TENSILE TEST STARTING");
  } else if (lastTextInput == "RAW"){
      currentState = RAWOUTPUT;
      Serial.println("Raw Scale Reading Mode");
  }else if (lastTextInput == "CAL"){
      currentState = LOADCAL;
      calState = CAL_IDLE;   // protection in case you run cal more than once in a single boot cycle
      Serial.println("Loadcell Calibration Mode");
  } else if (lastTextInput == "STOP"){
      currentState = FINISHED;
      Serial.println("COMMANDED TO FINISH");
  } else if (lastTextInput == "TARE"){
      if (currentState == IDLE){
        scale.tare();
        Serial.println("SCALE TARED");
      } else{
        Serial.println("TARE ONLY ALLOWED IN IDLE");
      }        
  } else if(lastTextInput == "ZERO"){
      // Send a single byte 'Z' (for ZERO) to the Nano
      Wire.beginTransmission(DRO_ADDR); 
      Wire.write('Z'); // 'Z' is what the nano is listening for
      Wire.endTransmission();
      Serial.println("DRO ZERO COMMAND SENT");
  } else if(lastTextInput.startsWith("JOGSPEED ")){ //for changing jogging speed
    int valueIndex = lastTextInput.indexOf(' '); // find index after the space
    String valueString = lastTextInput.substring(valueIndex +1); //treat everything after this position as a number
    float newSpeed = valueString.toFloat(); //convert to a float
    if (newSpeed > 0 && newSpeed <= jogMax){ // sets bounds for allowed values
      actualJogSpeed = newSpeed;
      jog_StepSpeed = ((actualJogSpeed/2)*10*200*microStep)/60;
      Serial.print("JOGSPEED SET to: ");
      Serial.print(actualJogSpeed, 1);
      Serial.println(" mm/min.");
    } else {
      Serial.print ("JOGSPEED OUT OF RANGE. MUST BE BETWEEN 0 AND "); // lets user know entered speed is invalid and what teh valid range is 
      Serial.println (jogMax,1);
    }
  
  }else if(lastTextInput.startsWith("TESTSPEED ")){ //for changing TEST SPEED
    int valueIndex = lastTextInput.indexOf(' ');
    String valueString = lastTextInput.substring(valueIndex +1);
    float newTestSpeed = valueString.toFloat();
    if (newTestSpeed > 0 && newTestSpeed <= jogMax){
      actualTestSpeed = newTestSpeed;
      test_StepSpeed = ((actualTestSpeed/2)*10*200*microStep)/60;
      Serial.print("TESTSPEED SET to: ");
      Serial.print(actualTestSpeed, 1);
      Serial.println(" mm/min.");
    } else {
      Serial.print("TESTSPEED OUT OF RANGE. MUST BE BETWEEN 0 AND ");
      Serial.println(jogMax, 1);
    }
  }else if(lastTextInput.startsWith("SAMPLERATE ")){ // set minimum ms between running data packets
    int valueIndex = lastTextInput.indexOf(' ');
    String valueString = lastTextInput.substring(valueIndex +1);
    long newInterval = valueString.toInt();
    if (newInterval >= 10 && newInterval <= 2000){
      testingSampleInterval = (unsigned long)newInterval;
      Serial.print("SAMPLERATE SET to: ");
      Serial.print(testingSampleInterval);
      Serial.println(" ms.");
    } else {
      Serial.println("SAMPLERATE OUT OF RANGE. MUST BE BETWEEN 10 AND 2000 ms.");
    }
  }else {Serial.println("UNKNOWN COMMAND. Please enter: IDLE, RUN_3PT, RUN_T, RAW, CAL, STOP, ZERO, TARE, JOGSPEED [value], TESTSPEED [value], or SAMPLERATE [value]");}
 }
}

/*                    DEFINING STATE MACHINE STATES                            */


//IDLE STATE
void updateIdle() {
if (millis() - lastIdleSampleTime >= idleSampleInterval) {
    lastIdleSampleTime = millis();
    Serial.print("Disp: "); Serial.print(CurrentDRO,3);
    Serial.print(" Load: "); Serial.print(CurrentLoad,3);
    Serial.print(" MotorState "); Serial.print(DriverEnableState);
    Serial.print(" Jog Speed "); Serial.print(actualJogSpeed); Serial.println("mm/min");
    
  }

    if (MotorEnable_bt.getSingleDebouncedPress()) {
        DriverEnableState = !DriverEnableState;
        digitalWrite(ENABLE, DriverEnableState);    
    }

     
  if (DriverEnableState == 0) {

    if (MotorUP_bt.isPressed()) {
      digitalWrite(DIR, HIGH);
      jog_StepSpeed = ((actualJogSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
      timerPeriodTicks = speedToTimerTicks(jog_StepSpeed);
      OCR1A = timerPeriodTicks;
      stepEnabled = true;
    }
    else if (MotorDWN_bt.isPressed()) {
      digitalWrite(DIR, LOW);
      jog_StepSpeed = ((actualJogSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
      timerPeriodTicks = speedToTimerTicks(jog_StepSpeed);
      OCR1A = timerPeriodTicks;
      stepEnabled = true;
    }
    else {
      stepEnabled = false;
    }
  }
}

//RUNNING 3 Point Bend STATE
void updateRunning_3PT() {
 if (currentState != previousState) {
    previousState = RUNNING_3PT;

    DriverEnableState = 0;
    digitalWrite(ENABLE, DriverEnableState);

    digitalWrite(DIR, LOW); //  - HIGH = TENSION, LOW = COMPRESSION
    test_StepSpeed = ((actualTestSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
    timerPeriodTicks = speedToTimerTicks(test_StepSpeed);
    OCR1A = timerPeriodTicks;
    stepEnabled = true;

    Wire.beginTransmission(DRO_ADDR);
    Wire.write('Z');
    Wire.endTransmission();

    scale.tare();

    // Reset averaging accumulators for new test
    loadAccum   = 0.0f;
    loadCount   = 0;
    lastSentDRO = -9999.0f;
    lastTestingSampleTime = millis();
  }

  // Accumulate every load reading
  loadAccum += CurrentLoad;
  loadCount++;

  // Emit one averaged packet per DRO tick (when displacement has changed AND
  // minimum sample interval has elapsed — prevents flooding if DRO glitches).
  bool droChanged  = fabsf(CurrentDRO - lastSentDRO) > 0.005f;
  bool intervalOk  = (millis() - lastTestingSampleTime) >= testingSampleInterval;
  if (droChanged && intervalOk) {
    float avgLoad = (loadCount > 0) ? (loadAccum / loadCount) : CurrentLoad;
    Serial.print("Disp: "); Serial.print(CurrentDRO, 3);
    Serial.print(" Load: "); Serial.println(avgLoad, 3);
    lastSentDRO = CurrentDRO;
    lastTestingSampleTime = millis();
    loadAccum = 0.0f;
    loadCount = 0;
  }

  if (CurrentDRO >= travelLimit) {
    Serial.println("TESTING ABORTED - TRAVEL LIMIT REACHED");
    currentState = FINISHED;
  } else if (CurrentLoad >= loadLimit) {
    Serial.println("TESTING ABORTED - LOAD LIMIT REACHED");
    currentState = FINISHED;
  }
}

//RUNNING TENSILE STATE
void updateRunning_T() {
 if (currentState != previousState) {
    previousState = RUNNING_T;

    DriverEnableState = 0;
    digitalWrite(ENABLE, DriverEnableState);

    digitalWrite(DIR, HIGH); // test direction - HIGH = TENSION, LOW = COMPRESSION
    test_StepSpeed = ((actualTestSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
    timerPeriodTicks = speedToTimerTicks(test_StepSpeed);
    OCR1A = timerPeriodTicks;
    stepEnabled = true;

    Wire.beginTransmission(DRO_ADDR);
    Wire.write('Z');
    Wire.endTransmission();

    scale.tare();

    // Reset averaging accumulators for new test
    loadAccum   = 0.0f;
    loadCount   = 0;
    lastSentDRO = -9999.0f;
    lastTestingSampleTime = millis();
  }

  // Accumulate every load reading
  loadAccum += CurrentLoad;
  loadCount++;

  // Emit one averaged packet per DRO tick
  bool droChanged  = fabsf(CurrentDRO - lastSentDRO) > 0.005f;
  bool intervalOk  = (millis() - lastTestingSampleTime) >= testingSampleInterval;
  if (droChanged && intervalOk) {
    float avgLoad = (loadCount > 0) ? (loadAccum / loadCount) : CurrentLoad;
    Serial.print("Disp: "); Serial.print(CurrentDRO, 3);
    Serial.print(" Load: "); Serial.println(avgLoad, 3);
    lastSentDRO = CurrentDRO;
    lastTestingSampleTime = millis();
    loadAccum = 0.0f;
    loadCount = 0;
  }

  if (CurrentDRO >= travelLimit) {
    Serial.println("TESTING ABORTED - TRAVEL LIMIT REACHED");
    currentState = FINISHED;
  } else if (CurrentLoad >= loadLimit) {
    Serial.println("TESTING ABORTED - LOAD LIMIT REACHED");
    currentState = FINISHED;
  }
}

//Raw scale Output STATE
void updateRawOutput() {
  if (millis() - lastIdleSampleTime >= idleSampleInterval) {
    lastIdleSampleTime = millis();
    //Serial.print("Disp: "); Serial.print(CurrentDRO,3);
    Serial.print(" Raw Reading: "); Serial.println(scale.read());
  }

  if (MotorEnable_bt.getSingleDebouncedPress()) {
        DriverEnableState = !DriverEnableState;
        digitalWrite(ENABLE, DriverEnableState);    
    }

     
  if (DriverEnableState == 0) {

    if (MotorUP_bt.isPressed()) {
      digitalWrite(DIR, HIGH);
      jog_StepSpeed = ((actualJogSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
      timerPeriodTicks = speedToTimerTicks(jog_StepSpeed);
      OCR1A = timerPeriodTicks;
      stepEnabled = true;
    }
    else if (MotorDWN_bt.isPressed()) {
      digitalWrite(DIR, LOW);
      jog_StepSpeed = ((actualJogSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
      timerPeriodTicks = speedToTimerTicks(jog_StepSpeed);
      OCR1A = timerPeriodTicks;
      stepEnabled = true;
    }
    else {
      stepEnabled = false;
    }
  }
}

//LOADCAL STATE
void updateLoadCal() {
// Allow manual jogging (same logic as IDLE)
  if (MotorEnable_bt.getSingleDebouncedPress()) {
      DriverEnableState = !DriverEnableState;
      digitalWrite(ENABLE, DriverEnableState);
  }

  if (DriverEnableState == 0) {

    if (MotorUP_bt.isPressed()) {
      digitalWrite(DIR, HIGH);
      jog_StepSpeed = ((actualJogSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
      timerPeriodTicks = speedToTimerTicks(jog_StepSpeed);
      OCR1A = timerPeriodTicks;
      stepEnabled = true;
    }
    else if (MotorDWN_bt.isPressed()) {
      digitalWrite(DIR, LOW);
      jog_StepSpeed = ((actualJogSpeed / 2.0) * 10 * 200 * microStep) / 60.0;
      timerPeriodTicks = speedToTimerTicks(jog_StepSpeed);
      OCR1A = timerPeriodTicks;
      stepEnabled = true;
    }
    else {
      stepEnabled = false;
    }
  }

  // --- Calibration State Machine ---
  switch(calState) {

    case CAL_IDLE:
      Serial.println("\nSTEP 1: Remove all load. Type ZERO and press enter.");
      calState = CAL_ZERO_WAIT;
      break;

    case CAL_ZERO_WAIT:
      if (lastTextInput == "ZERO") {
        Serial.println("Averaging 20 readings for offset...");
        scale.tare(20);
        newOffset = scale.get_offset();
        Serial.print("OFFSET = ");
        Serial.println(newOffset);
        Serial.println("\nApply known load and type WEIGHT <value>");
        calState = CAL_WEIGHT_WAIT;
      }
      break;

    case CAL_WEIGHT_WAIT:
      if (lastTextInput.startsWith("WEIGHT ")) {

        int idx = lastTextInput.indexOf(' ');
        calWeight = lastTextInput.substring(idx+1).toFloat();

        Serial.print("Entered weight: ");
        Serial.println(calWeight, 3);

        Serial.println("Calculating scale...");
        scale.calibrate_scale(calWeight, 10);
        newScale = scale.get_scale();

        Serial.print("SCALE = ");
        Serial.println(newScale, 6);

        Serial.println("\nFINAL VALUES:");
        Serial.print("scale.set_offset(");
        Serial.print(newOffset);
        Serial.println(");");
        Serial.print("scale.set_scale(");
        Serial.print(newScale, 6);
        Serial.println(");");

        Serial.println("\nType IDLE to exit calibration.");
        calState = CAL_DONE;
      }
      break;

    case CAL_DONE:
      break;
  }

}

//ESTOPPED STATE
void updateEStop() {
  if (millis() - lastIdleSampleTime >= idleSampleInterval) {
    lastIdleSampleTime = millis();
    Serial.print("Disp: "); Serial.print(CurrentDRO,3);
    Serial.print(" Load: "); Serial.println(CurrentLoad,3);
    Serial.println("MACHINE IS E-STOPPED - ENTER \"IDLE\" TO RETURN TO IDLE");
  }
}


void ESTOP_ISR(){
  estopTriggered = true;
 }