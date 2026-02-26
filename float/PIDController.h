#include <algorithm>

class PIDController {
private:
    double Kp, Ki, Kd;          
    double previousError;        
    double integral;             
    double outputMin, outputMax; 

public:
    PIDController(double p, double i, double d, double outMin = -1e9, double outMax = 1e9);

    // compute control signal given current depth and setpoint
    // dt is the time elapsed since last call (seconds)
    double calculateControlSignal(double setpoint, double measuredValue, double dt);

    // reset the integral and derivative history 
    void reset();

    // update tuning parameters at runtime
    void setTunings(double p, double i, double d);

    // set output limits (e.g. min/max syringe displacement command)
    void setOutputLimits(double minVal, double maxVal);
};