#include <Arduino.h>
#include <AFMotor.h>

#define BASE_SPEED 200
#define TURN_SPEED 150
#define SEARCH_SPEED 150
#define THRESHOLD 500
#define YELLOW_MIN 20
#define YELLOW_MAX 29

// Fuzzy controller membership ranges
#define BLACK_LOW 0
#define BLACK_HIGH 250
#define DARK_GREY_LOW 125
#define DARK_GREY_HIGH 500
#define TRANSITION_LOW 300
#define TRANSITION_HIGH 750
#define BACKGROUND_LOW 750
#define BACKGROUND_HIGH 1023

AF_DCMotor motor1(1);
AF_DCMotor motor2(2);
AF_DCMotor motor3(3);
AF_DCMotor motor4(4);

byte ir_right = A5;
byte ir_left = A4;

int left_speed = 0;
int right_speed = 0;
int state = 0;

// Startup pause variables
bool is_startup_paused = false;
unsigned long startup_pause_start = 0;
const unsigned long startup_pause_duration = 10000; // 10 seconds pause at startup

// Marker detection variables
bool marker_detected = false;
bool is_marker_paused = false;
unsigned long marker_pause_start = 0;
const unsigned long marker_pause_duration = 10000; // 10 seconds pause when office marker detected
int yellow_detection_count = 0;

// Office markers detected (2 offices, then base)
int office_marker_count = 0;
const int TOTAL_OFFICE_MARKERS = 2;
bool is_base_reached = false;
bool robot_finished = false;

// Cooldown to prevent re-detecting same marker
bool marker_cooldown = false;
unsigned long cooldown_start = 0;
const unsigned long cooldown_duration = 2000; // 2 seconds cooldown after pause

// Delay before pause after detection
bool delay_before_pause = false;
unsigned long detection_time = 0;
const unsigned long delay_duration = 500; // 0.5 seconds delay before pausing

// Fuzzy membership function results
float left_black = 0, left_dark_grey = 0, left_transition = 0, left_background = 0;
float right_black = 0, right_dark_grey = 0, right_transition = 0, right_background = 0;

// Fuzzy output speeds (initialized)
float m1_speed = 0, m2_speed = 0, m3_speed = 0, m4_speed = 0;

void controller(int, int);
void drive_all_motors(int, int);
void fuzzy_membership(int value, float &black, float &dark_grey, float &transition, float &background);
void fuzzy_inference(float l_black, float l_dark, float l_trans, float l_bg,
                     float r_black, float r_dark, float r_trans, float r_bg,
                     float &out1, float &out2, float &out3, float &out4);
void fuzzy_defuzzify(float out1, float out2, float out3, float out4, int &left_speed, int &right_speed);

// Fuzzy membership function for sensor values
void fuzzy_membership(int value, float &black, float &dark_grey, float &transition, float &background)
{
    // Black membership (0-250, peak at 0)
    if (value <= 0) black = 1.0;
    else if (value < 250) black = 1.0 - (value / 250.0);
    else black = 0.0;
    
    // Dark grey membership (125-500, center at 312.5)
    if (value <= 125) dark_grey = 0.0;
    else if (value < 312.5) dark_grey = (value - 125) / 187.5;
    else if (value < 500) dark_grey = 1.0 - ((value - 312.5) / 187.5);
    else dark_grey = 0.0;
    
    // Transition membership (300-750, center at 525)
    if (value <= 300) transition = 0.0;
    else if (value < 525) transition = (value - 300) / 225.0;
    else if (value < 750) transition = 1.0 - ((value - 525) / 225.0);
    else transition = 0.0;
    
    // Background membership (750-1023, peak at 1023)
    if (value <= 750) background = 0.0;
    else if (value < 886.5) background = (value - 750) / 136.5;
    else background = 1.0;
}

// Fuzzy inference engine
void fuzzy_inference(float l_black, float l_dark, float l_trans, float l_bg,
                     float r_black, float r_dark, float r_trans, float r_bg,
                     float &out1, float &out2, float &out3, float &out4)
{
    // Rule 1: Both sensors on blackm, Then go straight
    float rule1 = min(l_black, r_black);
    out1 = max(out1, rule1 * 200);  // motor1 forward
    out2 = max(out2, rule1 * 200);  // motor2 forward
    out3 = max(out3, rule1 * 200);  // motor3 forward
    out4 = max(out4, rule1 * 200);  // motor4 forward
    
    // Rule 2: Left black, right dark grey, Then slight right turn
    float rule2 = min(l_black, r_dark);
    out1 = max(out1, rule2 * 180);  // motor1 forward
    out2 = max(out2, rule2 * 150);  // motor2 forward (slower)
    out3 = max(out3, rule2 * 150);  // motor3 forward (slower)
    out4 = max(out4, rule2 * 180);  // motor4 forward
    
    // Rule 3: Left dark grey, right black, Then slight left turn
    float rule3 = min(l_dark, r_black);
    out1 = max(out1, rule3 * 150);  // motor1 forward (slower)
    out2 = max(out2, rule3 * 180);  // motor2 forward
    out3 = max(out3, rule3 * 180);  // motor3 forward
    out4 = max(out4, rule3 * 150);  // motor4 forward (slower)
    
    // Rule 4: Left black, right transition, Then medium right turn
    float rule4 = min(l_black, r_trans);
    out1 = max(out1, rule4 * 200);   // motor1 forward
    out2 = max(out2, rule4 * 100);   // motor2 forward (slow)
    out3 = max(out3, rule4 * 100);   // motor3 forward (slow)
    out4 = max(out4, rule4 * 200);   // motor4 forward
    
    // Rule 5: Left transition, right black, Then medium left turn
    float rule5 = min(l_trans, r_black);
    out1 = max(out1, rule5 * 100);   // motor1 forward (slow)
    out2 = max(out2, rule5 * 200);   // motor2 forward
    out3 = max(out3, rule5 * 200);   // motor3 forward
    out4 = max(out4, rule5 * 100);   // motor4 forward (slow)
    
    // Rule 6: Left black, right background, Then sharp right turn
    float rule6 = min(l_black, r_bg);
    out1 = max(out1, rule6 * 200);   // motor1 forward
    out2 = max(out2, rule6 * -150);  // motor2 backward
    out3 = max(out3, rule6 * -150);  // motor3 backward
    out4 = max(out4, rule6 * 200);   // motor4 forward
    
    // Rule 7: Left background, right black, Then sharp left turn
    float rule7 = min(l_bg, r_black);
    out1 = max(out1, rule7 * -150);  // motor1 backward
    out2 = max(out2, rule7 * 200);   // motor2 forward
    out3 = max(out3, rule7 * 200);   // motor3 forward
    out4 = max(out4, rule7 * -150);  // motor4 backward
    
    // Rule 8: Both sensors on transition or background, Then rotate/search
    float rule8 = max(min(l_trans, r_trans), min(l_bg, r_bg));
    out1 = max(out1, rule8 * -150);  // motor1 backward (rotate)
    out2 = max(out2, rule8 * 150);   // motor2 forward
    out3 = max(out3, rule8 * 150);   // motor3 forward
    out4 = max(out4, rule8 * -150);  // motor4 backward (rotate)
    
    // Rule 9: Left dark grey, right transition, Then gentle right turn
    float rule9 = min(l_dark, r_trans);
    out1 = max(out1, rule9 * 180);   // motor1 forward
    out2 = max(out2, rule9 * 130);   // motor2 forward
    out3 = max(out3, rule9 * 130);   // motor3 forward
    out4 = max(out4, rule9 * 180);   // motor4 forward
    
    // Rule 10: Left transition, right dark grey, Then gentle left turn
    float rule10 = min(l_trans, r_dark);
    out1 = max(out1, rule10 * 130);  // motor1 forward
    out2 = max(out2, rule10 * 180);  // motor2 forward
    out3 = max(out3, rule10 * 180);  // motor3 forward
    out4 = max(out4, rule10 * 130);  // motor4 forward
}

// Defuzzification using centroid method
void fuzzy_defuzzify(float out1, float out2, float out3, float out4, int &left_speed, int &right_speed)
{
    // Sum of all output memberships
    float sum1 = abs(out1);
    float sum2 = abs(out2);
    float sum3 = abs(out3);
    float sum4 = abs(out4);
    
    // If all outputs are zero, search mode
    if (sum1 < 0.01 && sum2 < 0.01 && sum3 < 0.01 && sum4 < 0.01) {
        left_speed = -SEARCH_SPEED;
        right_speed = SEARCH_SPEED;
        return;
    }
    
    // Normalize and scale to motor speed range
    float max_sum = max(max(sum1, sum2), max(sum3, sum4));
    if (max_sum > 0) {
        out1 = (out1 / max_sum) * 255;
        out2 = (out2 / max_sum) * 255;
        out3 = (out3 / max_sum) * 255;
        out4 = (out4 / max_sum) * 255;
    }
    
    // For differential drive, combine motor pairs
    // Left side: motors 1 and 4
    left_speed = constrain((out1 + out4) / 2, -255, 255);
    // Right side: motors 2 and 3
    right_speed = constrain((out2 + out3) / 2, -255, 255);
}

void controller(int sensor1, int sensor2)
{
    // Reset fuzzy outputs
    float out1 = 0, out2 = 0, out3 = 0, out4 = 0;
    
    // Calculate membership values for left sensor
    fuzzy_membership(sensor1, left_black, left_dark_grey, left_transition, left_background);
    
    // Calculate membership values for right sensor
    fuzzy_membership(sensor2, right_black, right_dark_grey, right_transition, right_background);
    
    // Perform fuzzy inference
    fuzzy_inference(left_black, left_dark_grey, left_transition, left_background,
                    right_black, right_dark_grey, right_transition, right_background,
                    out1, out2, out3, out4);
    
    // Defuzzify to get motor speeds
    fuzzy_defuzzify(out1, out2, out3, out4, left_speed, right_speed);
    
    // Update state for debugging
    if (left_speed > 50 && right_speed > 50) state = 1;
    else if (left_speed > right_speed) state = 2;
    else if (right_speed > left_speed) state = 3;
    else state = 4;
}

void setup()
{
    // Stop all motors on startup
    motor1.run(RELEASE);
    motor2.run(RELEASE);
    motor3.run(RELEASE);
    motor4.run(RELEASE);
    
    motor1.setSpeed(0);
    motor2.setSpeed(0);
    motor3.setSpeed(0);
    motor4.setSpeed(0);
    
    pinMode(A5, INPUT);
    pinMode(A4, INPUT);
    
    motor1.setSpeed(255);
    motor2.setSpeed(255);
    motor3.setSpeed(255);
    motor4.setSpeed(255);
    
    // Start the 10-second startup pause
    is_startup_paused = true;
    startup_pause_start = millis();
}

void loop()
{
    // Check if robot is in startup pause
    if (is_startup_paused)
    {
        // Keep motors stopped
        drive_all_motors(0, 0);
        
        // Check if 10-second startup pause is over
        if (millis() - startup_pause_start >= startup_pause_duration)
        {
            is_startup_paused = false;
        }
        
        delay(100);
        return;
    }
    
    // Check if robot has finished (base reached)
    if (robot_finished)
    {
        // Keep motors stopped forever
        drive_all_motors(0, 0);
        delay(100);
        return;
    }
    
    int left_val = analogRead(ir_left);
    int right_val = analogRead(ir_right);
    
    // Check if robot is paused due to office marker detection
    if (is_marker_paused)
    {
        // Keep motors stopped
        drive_all_motors(0, 0);
        
        // Check if 10-second marker pause is over
        if (millis() - marker_pause_start >= marker_pause_duration)
        {
            is_marker_paused = false;
            marker_detected = false;
            yellow_detection_count = 0;
            
            // Start cooldown to prevent re-detecting same marker
            marker_cooldown = true;
            cooldown_start = millis();
        }
        
        delay(100);
        return;
    }
    
    // Check if in cooldown period (prevents re-detecting same marker)
    if (marker_cooldown)
    {
        if (millis() - cooldown_start >= cooldown_duration)
        {
            marker_cooldown = false; // Cooldown finished
        }
        else
        {
            // During cooldown, just follow the line normally
            controller(left_val, right_val);
            drive_all_motors(left_speed, right_speed);
            delay(10);
            return;
        }
    }
    
    // Check if in delay-before-pause period
    if (delay_before_pause)
    {
        // Continue following line during delay
        controller(left_val, right_val);
        drive_all_motors(left_speed, right_speed);
        
        // Check if 0.5 seconds has passed
        if (millis() - detection_time >= delay_duration)
        {
            delay_before_pause = false;
            
            // Now pause the robot
            marker_detected = true;
            is_marker_paused = true;
            marker_pause_start = millis();
            
            // Stop motors immediately
            drive_all_motors(0, 0);
            yellow_detection_count = 0;
            
            delay(50);
            return;
        }
        
        delay(10);
        return;
    }
    
    // YELLOW MARKER DETECTION
    if (!marker_detected && !marker_cooldown && !delay_before_pause)
    {
        bool left_yellow = (left_val >= YELLOW_MIN && left_val <= YELLOW_MAX);
        bool right_yellow = (right_val >= YELLOW_MIN && right_val <= YELLOW_MAX);
        
        if (left_yellow || right_yellow)
        {
            yellow_detection_count++;
            
            // Need 2 consecutive detections to confirm
            if (yellow_detection_count >= 2)
            {
                // Increment office marker count
                office_marker_count++;
                
                // Check if this is the base marker (3rd marker)
                if (office_marker_count > TOTAL_OFFICE_MARKERS)
                {
                    // BASE REACHED, Stop forever
                    is_base_reached = true;
                    robot_finished = true;
                    drive_all_motors(0, 0);
                    yellow_detection_count = 0;
                    delay(50);
                    return;
                }
                else
                {
                    // Office marker detected, start 0.5 second delay before pausing
                    delay_before_pause = true;
                    detection_time = millis();
                    yellow_detection_count = 0;
                    
                    delay(50);
                    return;
                }
            }
        }
        else
        {
            yellow_detection_count = 0;
        }
    }
    
    // Normal line following with fuzzy logic
    controller(left_val, right_val);
    drive_all_motors(left_speed, right_speed);
    
    delay(10);
}

void drive_all_motors(int left, int right)
{
    left = constrain(left, -255, 255);
    right = constrain(right, -255, 255);
    
    if (left > 0)
    {
        motor1.setSpeed(left);
        motor4.setSpeed(left);
        motor1.run(FORWARD);
        motor4.run(BACKWARD);
    }
    else if (left < 0)
    {
        motor1.setSpeed(-left);
        motor4.setSpeed(-left);
        motor1.run(BACKWARD);
        motor4.run(FORWARD);
    }   
    else
    {
        motor1.run(RELEASE);
        motor4.run(RELEASE);
    }
    
    if (right > 0)
    {
        motor2.setSpeed(right);
        motor3.setSpeed(right);
        motor2.run(BACKWARD);
        motor3.run(FORWARD);
    }
    else if (right < 0)
    {
        motor2.setSpeed(-right);
        motor3.setSpeed(-right);
        motor2.run(FORWARD);
        motor3.run(BACKWARD);
    }   
    else
    {
        motor2.run(RELEASE);
        motor3.run(RELEASE);
    }
}