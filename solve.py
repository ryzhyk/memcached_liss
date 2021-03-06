import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import fsolve
from scipy.interpolate import interp1d

def interpolate_l (l):
    x,y = zip(*l.items())

    ll = interp1d(x, y)
    xx = np.linspace(1, max(x), 100)
    
    plt.plot(xx,ll(xx),'r|', x,y,'bo')
    plt.legend(['data'], loc='best')
    plt.show()
    return lambda ns: ll(np.maximum(ns, np.ones_like(ns)))


def solve_nn (n, c, cc, l, sections):
    ll = interpolate_l(l)
    func = lambda nn : 1 - nn + (n-1) * ((cc + sections*ll(nn)) * np.maximum(nn-0.5,np.ones_like(nn))) / (c - cc + (cc + sections*ll(nn)) * np.maximum(nn-0.5,np.ones_like(nn)))

    # Plot it
    nn_range = np.linspace(1, max(l.keys()), 100)

    plt.plot(nn_range, func(nn_range))
    plt.xlabel("n'")
    plt.ylabel("expression value")
    plt.grid()
    plt.show()

    # Use the numerical solver to find the roots

    nn_initial_guess = n
    sols = fsolve(func, nn_initial_guess)
    if len(sols) == 0:
        return 1
    else:
        return sols[0]

#print "The solution is tau = %f" % tau_solution
#print "at which the value of the expression is %f" % func(tau_solution)

