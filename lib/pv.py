#!/usr/bin/python
"""Epics Process Variable

"""
import time
import math
import copy

import ca
import dbr

def fmt_time(t=None):
    if t is None: t = time.time()
    t,frac=divmod(t,1)
    return "%s.%3.3i" %(time.strftime("%Y-%h-%d %H:%M:%S"),1000.0*frac)

# retrieve pv object by name
PV_cache = {}

_PV_fields_ = ('pvname','value','char_value', 'status','ftype',
               'chid', 'host','count','access','write_access',
               'severity', 'timestamp', 'precision',
               'units', 'enum_strs','no_str',
               'upper_disp_limit', 'lower_disp_limit',
               'upper_alarm_limit', 'lower_alarm_limit',
               'lower_warning_limit','upper_warning_limit',
               'upper_ctrl_limit', 'lower_ctrl_limit')

class PV(object):
    """== Epics Process Variable
    
    A PV encapsulates an Epics Process Variable.
   
    The primary interface methods for a pv are to get() and put() is value:
      >>>p = PV(pv_name)    # create a pv object given a pv name
      >>>p.get()            # get pv value
      >>>p.put(val)         # set pv to specified value. 

    Additional important attributes include:
      >>>p.pvname           # name of pv
      >>>p.value            # pv value (can be set or get)
      >>>p.char_value       # string representation of pv value
      >>>p.count            # number of elements in array pvs
      >>>p.type             # EPICS data type: 'string','double','enum','long',....
"""

    def __init__(self,pvname, callback=None, form='native',
                 verbose=False, auto_monitor=True):

        self.pvname  = pvname.strip()
        self.verbose = verbose
        self.auto_monitor = auto_monitor
        self._form   = {'ctrl': (form.lower() =='ctrl'),
                        'time': (form.lower() =='time')}

        self.callbacks = {}
        if callable(callback): self.callbacks[0] = (callback,{})

        self.connected  = False
        self._args      = {}.fromkeys(_PV_fields_)

        self._args['pvname'] = self.pvname
        self.__mondata = None
        self.chid = ca.create_channel(self.pvname,
                                      userfcn=self._onConnect)
        self._args['chid'] = self.chid
        self._args['pvid'] = id(self)
        PV_cache[id(self)] = self

        try:
            self._args['type'] = dbr.Name(ca.field_type(self.chid)).lower()
        except:
            self._args['type'] = 'unknown'

            
    def _onConnect(self,chid=0,conn=True,**kw):
        self.connected = conn
        if self.connected:
            self._args['host']   = ca.host_name(self.chid)
            self._args['count']  = ca.element_count(self.chid)
            self._args['access'] = ca.access(self.chid)
            self._args['write_access'] = ca.write_access(self.chid)
            self.ftype  = ca.promote_type(self.chid,
                                     use_ctrl=self._form['ctrl'],
                                     use_time=self._form['time'])
            self._args['type'] = dbr.Name(self.ftype).lower()
        return

    def connect(self,timeout=5.0,force=True):
        if not self.connected:
            ca.connect_channel(self.chid, timeout=timeout,force=force)
            self.poll()
        if (self.connected and
            self.auto_monitor and
            self.__mondata is None):
            self.__mondata = ca.subscribe(self.chid,
                                          userfcn=self._onChanges,
                                          use_ctrl=self._form['ctrl'],
                                          use_time=self._form['time'])
        return self.connected

    def poll(self,t1=1.e-3,t2=1.0):    ca.poll(t1,t2)

    def get(self, as_string=False):
        """returns current value of PV
        use argument 'as_string=True' to
        return string representation

        >>> p.get('13BMD:m1.DIR')
        0
        >>> p.get('13BMD:m1.DIR',as_string=True)
        'Pos'
        """
        if not self.connect(force=False):  return None
        self._args['value'] = ca.get(self.chid,
                                    ftype=self.ftype)
        self.poll() 
        self._set_charval(self._args['value'])

        field = 'value'
        if as_string: field = 'char_value'
        return self._args[field]

    def put(self,value,wait=False,timeout=30.0,callback=None):
        """set value for PV, optionally waiting until
        the processing is complete.
        """
        if not self.connect(force=False):  return None
        return ca.put(self.chid, value,
                      wait=wait,
                      timeout=timeout,
                      callback=callback)


    def _set_charval(self,val,ca_calls=True):
        """ set the character representation of the value"""

        ftype = self._args['ftype']
        cval  = repr(val)       
        if ftype == dbr.STRING: cval = val
        
        if self._args['count'] > 1:
            if ftype == dbr.CHAR:
                cval = ''.join([chr(i) for i in val]).rstrip()
            else:
                cval = '<array size=%d, type=%s>' % (len(val),
                                                     dbr.Name(ftype))
        elif ftype in (dbr.FLOAT, dbr.DOUBLE):
            if ca_calls and self._args['precision'] is None:
                self.get_ctrlvars()
            try: 
                fmt  = "%%.%if"
                if 4 < abs(int(math.log10(abs(val + 1.e-9)))):
                    fmt = "%%.%ig"
                cval = (fmt % self._args['precision']) % val                    
            except:
                pass 
        elif ftype == dbr.ENUM:
            if ca_calls and self._args['enum_strs'] in ([], None):
                self.get_ctrlvars()
            try:
                cval = self._args['enum_strs'][val]
            except:
                pass

        self._args['char_value'] =cval
        return cval

    
    def get_ctrlvars(self):
        if not self.connect(force=False):  return None
        kw = ca.get_ctrlvars(self.chid)
        self._args.update(kw)
        return kw

    def _onChanges(self, value=None, **kw):
        """built-in callback function: this should not be overwritten!!"""
        self._args.update(kw)
        self._args['value']  = value
        self._args['timestamp'] = kw.get('timestamp',time.time())

        self._set_charval(self._args['value'],ca_calls=False)

        if self.verbose:
            print '  %s: %s (%s)'% (self.pvname,self._args['char_value'],
                                    fmt_time(self._args['timestamp']))
        
        if True:
            for index in self.callbacks:
                fcn,kwargs = self.callbacks[index]            
                kw = copy.copy(self._args)
                kw.update(kwargs)
                kw['cb_index'] = index
                if callable(fcn):  fcn(**kw)
        # Note: runtime errors can occur if the callback function
        # is no longer available, as from a GUI toolkit
        else:
            pass
            
    def add_callback(self,callback=None,**kw):
        if callable(callback):
            n_cb = len(self.callbacks)                
            index = n_cb + 1
            if index > 512 and index > 2*n_cb:
                nx = None
                for i in range(index):
                    if i not in self.callbacks:
                        nx = i
                        break
                if nx is not None: index = i
            self.callbacks[index] = (callback,kw)
        return index
    
    def remove_callback(self,index=None):
        if index is None and len(self.callbacks)==1:
            index = self.callbacks.keys()[0]
            
        if index in self.callbacks:
            x = self.callbacks.pop(index)
        ca.poll()

    def clear_callbacks(self,**kw):
        self.callbacks = {}

    def _getinfo(self):
        if not self.connect(force=False):  return None
        if self._args['precision'] is None: self.get_ctrlvars()

        out = []
        # list basic attributes
        mod   = 'native'
        xtype = self._args['type']
        if '_' in xtype: mod,xtype = ftype.split('_')

        out.append("== %s  (%s) ==" % (self.pvname,xtype))

        if self.count==1:
            val = self._args['value']
            fmt = '%i'
            if   xtype in ('float','double'): fmt = '%g'
            elif xtype in ('string','char'):  fmt = '%s'
            out.append('   value      = %s' % fmt % val)

        else:
            aval,ext,fmt = [],'',"%i,"
            if self.count>5: ext = '...'
            if xtype in  ('float','double'): fmt = "%g,"
            for i in range(min(5,self.count)):
                aval.append(fmt % self._args['value'][i])
            out.append("   value      = array  [%s%s]" % ("".join(aval),ext))

        for i in ('char_value','count','type','units',
                  'precision','host','access',
                  'status','severity','timestamp',
                  'upper_ctrl_limit', 'lower_ctrl_limit',
                  'upper_disp_limit', 'lower_disp_limit',
                  'upper_alarm_limit', 'lower_alarm_limit',
                  'upper_warning_limit','lower_warning_limit'):
            if hasattr(self,i):
                att = getattr(self,i)
                if i == 'timestamp': att = "%.3f (%s)" % (att,fmt_time(att))
                if att is not None:
                    if len(i) < 12:
                        out.append('   %.11s= %s' % (i+' '*12, str(att)))
                    else:
                        out.append('   %.20s= %s' % (i+' '*20, str(att)))

        if xtype == 'enum':  # list enum strings
            out.append('   enum strings: ')
            for i,s in enumerate(self.enum_strs):
                out.append("       %i = %s " % (i,s))

        if self.__mondata is not None:
            out.append('   PV is monitored internally')
            if len(self.callbacks) > 0:
                out.append("   user-defined callbacks:")
                for i in cbs:  out.append('      %s' % (i.func_name))
            else:
                out.append("   no user callbacks are defined.")
        else:
            out.append('   PV is not monitored internally')
        out.append('=============================')
        return '\n'.join(out)
        
    def _getarg(self,arg):
        if self._args['value'] is None:  self.get()
        return self._args.get(arg,None)
        
    @property
    def value(self):     return self._getarg('value')

    @value.setter
    def value(self,v):   return self.put(v)

    @property
    def char_value(self): return self._getarg('char_value')

    @property
    def status(self): return self._getarg('status')

    @property
    def type(self): return self._args['type']

    @property
    def host(self): return self._getarg('host')

    @property
    def count(self): return self._getarg('count')

    @property
    def access(self): return self._getarg('access')

    @property
    def write_access(self): return self._getarg('write_access')

    @property
    def severity(self): return self._getarg('severity')

    @property
    def timestamp(self): return self._getarg('timestamp')

    @property
    def precision(self): return self._getarg('precision')

    @property
    def units(self): return self._getarg('units')

    @property
    def enum_strs(self): return self._getarg('enum_strs')

    @property
    def no_str(self): return self._getarg('no_str')

    @property
    def upper_disp_limit(self): return self._getarg('upper_disp_limit')

    @property
    def lower_disp_limit(self): return self._getarg('lower_disp_limit')

    @property
    def upper_alarm_limit(self): return self._getarg('upper_alarm_limit')

    @property
    def lower_alarm_limit(self): return self._getarg('lower_alarm_limit')

    @property
    def lower_warning_limit(self): return self._getarg('lower_warning_limit')

    @property
    def upper_warning_limit(self): return self._getarg('upper_warning_limit')

    @property
    def upper_ctrl_limit(self): return self._getarg('upper_ctrl_limit')

    @property
    def lower_ctrl_limit(self): return self._getarg('lower_ctrl_limit')

    @property
    def info(self): return self._getinfo()

    def __repr__(self):
        if not self.connected:  return "<PV '%s': not connected>" % self.pvname

        return "<PV: '%(pvname)s', count=%(count)i, type=%(ftype)s, access=%(access)s>" % self._args
    
    def __str__(self): return self.__repr__()

    def __eq__(self,other):
        try:
            return (self._chid  == other._chid)
        except:
            return False
        
