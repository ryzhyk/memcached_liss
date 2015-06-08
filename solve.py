import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import fsolve
from scipy.interpolate import interp1d

def interpolate_l (l):
    x,y = zip(*l.items())

    ll = interp1d(x, y, 'cubic')
    xx = np.linspace(1, max(x), 100)
    
    plt.plot(xx,ll(xx),'r|', x,y,'bo')
    plt.legend(['data', 'cubic'], loc='best')
    plt.show()
    return ll


def solve_nn (n, c, cc, l):
    ll = interpolate_l(l)
    func = lambda nn : 1 - nn + (n-1) * ((cc + ll(nn)) * nn) / (c - cc + (cc + ll(nn)) * nn)

    # Plot it
    nn_range = np.linspace(1, max(l.keys()), 100)

    plt.plot(nn_range, func(nn_range))
    plt.xlabel("n'")
    plt.ylabel("expression value")
    plt.grid()
    plt.show()

    # Use the numerical solver to find the roots

    nn_initial_guess = n
    return fsolve(func, nn_initial_guess)

#print "The solution is tau = %f" % tau_solution
#print "at which the value of the expression is %f" % func(tau_solution)

