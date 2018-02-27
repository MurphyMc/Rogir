import os
import sys
from etree_patch import ET, patch_et
import logging
level = logging.DEBUG
level = logging.ERROR
try:
  import coloredlogs
  coloredlogs.DEFAULT_LOG_FORMAT = '%(levelname)-8s %(name)-15s %(message)s'
  coloredlogs.install()
  coloredlogs.set_level(level)
except Exception:
  logging.basicConfig(level=level)


gir_nsmap = {'glib': 'http://www.gtk.org/introspection/glib/1.0', 'c': 'http://www.gtk.org/introspection/c/1.0', None: 'http://www.gtk.org/introspection/core/1.0'}
ns_c = "{%s}" % (gir_nsmap['c'],)
ns_gir = "{%s}" % (gir_nsmap[None],)
ns_glib = "{%s}" % (gir_nsmap['glib'],)
patch_et(gir_nsmap)

class NO_DEFAULT (object):
  pass

_squelched = set()
def squelch (f, msg, *args):
  if args: msg = msg % args
  if msg in _squelched: return
  _squelched.add(msg)
  if len(_squelched) > 2000: _squelched.clear()
  f(msg)

@staticmethod
def Bool (v):
  v = str(v).lower()
  return v in ("1", "true")


src_dir = "/usr/share/gir-1.0"






def escape (s):
  if isinstance(s, (str,unicode)):
    x = repr(s)
    if x.startswith("'") and x.endswith("'"):
      s = s + "'"
      s = repr(s)
      assert s.endswith("'\"")
      assert s.startswith('"')
      return s[:-2] + '"'
    return x
  return str(s)



no_type_warnings = set()
type_log = logging.getLogger("types")


class RogirType (object):
  gval = None
  is_numeric = False
  _is_reference = False
  _is_array = False
  is_boolean = False


  @property
  def _root_type (self):
    p = getattr(self, "_parent_type", None)
    if not p: return self
    return p._root_type

  @property
  def _rshort (self):
    return self._rname.split("::")[-1]

class ImportedType (RogirType):
  @property
  def _rname (self):
    if hasattr(self, "rname"): return self.rname
    return self._get_ancestor(Namespace).name + "::" + valid_name(self.name)

  def _nread (self, n):
    return "(($%s)->_self)" % (valid_name(n),)

  def _new (self, n, native_v=None, v=None):
    assert native_v is not None or v is not None
    assert v is None
    if v is None: v = '(native("(intptr_t)(%s)")->IntPtr)' % (native_v,)
    return "%s = %s._create_(%s)" % (valid_name(n), self._rname, v)




class GIRNodeMeta (type):
  def __new__(cls, name, parents, dct):
    t = super(GIRNodeMeta, cls).__new__(cls, name, parents, dct)
    try:
      GIRNode.SUBCLASSES[name] = t
    except Exception:
      pass
    return t


def split_up (s):
  kvs = {}
  ss = s.split("\n")
  for s in ss:
    s = s.strip()
    if not s: continue
    if s.startswith("#"): continue
    k,v = s.split(None, 1)
    kvs[k] = v
  return kvs

name_map = split_up("""
  class       cls
  loop        loop_
  type_name   typename
  instance    instance_
  use         use_
  native      native_
  SCALE       SCALE_
  false       false_
  true        true_
  step        step_
  module      module_
""")

def valid_name (n):
  n = n.replace("-","_")
  if n[0].isdigit():
    n = "_" + n
  return name_map.get(n, n)


class GIRNode (object):
  __metaclass__ = GIRNodeMeta
  EL_NAME = None
  AUTO_PARSE = {}
  ALL = []
  SUBCLASSES = {}
  PARENT = None

  def _get_ancestor (self, t):
    if isinstance(self, t): return self
    if not self.PARENT: return None
    return self.PARENT._get_ancestor(t)

  @property
  def _namespace_name (self):
    return self._get_ancestor(Namespace).name

  @property
  def log (self):
    l = getattr(self, "_log", None)
    if l: return l
    if self.PARENT:
      return self.PARENT.log
    self._log = logging.getLogger("root")
    return self._log

  @classmethod
  def parse (cls, node, module=None, el_name=None):
    def msetattr (o, n, v):
      c = getattr(o, n, NO_DEFAULT)
      ct = getattr(o, "_PARSE_" + n, None)
      if c is NO_DEFAULT:
        pass
      elif ct:
        v = ct(v)
      else:
        base = getattr(type(o), n, NO_DEFAULT)
        if base != c:
          raise RuntimeError("Attribute %s on %s already set" % (n, o))
      setattr(o, n, v)
    try:
      if cls.ALL is GIRNode.ALL:
        cls.ALL = []

      self = cls()
      self.EL_NAME = el_name
      self._node = node
      self._module = module
      for a,v in node.attrib.items():
        if a.startswith("{"):
          ns = a[1:a.find("}")]
          rest = a[a.find("}") + 1:]
          rev = {v:k for k,v in gir_nsmap.items()}
          nice = rev.get(ns)
          if not nice: continue
          msetattr(self, valid_name(nice + "__" + rest), v)
          a = rest
        else:
          a = valid_name(a)
          msetattr(self, a, v)
      for n,t in cls.AUTO_PARSE.items():
        real_n = n
        if n.startswith("{"):
          ns = n[1:n.find("}")]
          rest = n[n.find("}") + 1:]
          rev = {v:k for k,v in gir_nsmap.items()}
          nice = rev.get(ns)
          if not nice: continue
          n = nice + "__" + rest
        n = valid_name(n)
        is_list = isinstance(t, list)
        if is_list:
          assert len(t) == 1
          t = t[0]
        if isinstance(t, str): t = GIRNode.SUBCLASSES[t]
        if is_list:
          l = []
          setattr(self, n, l)
        else:
          setattr(self, n, None)
        vs = node.findall(real_n)
        if not is_list: assert len(vs) <= 1, "More than one %s in %s" % (n, self.name)
        for v in vs:
          new = t.parse(v, el_name=real_n)
          if new and new.is_valid:
            new.PARENT = self
            if is_list:
              l.append(new)
            else:
              setattr(self, n, new)

      if self.is_valid:
        cls.ALL.append(self)
        self._init()
        return self

    except Exception as e:
      print "While parsing %s (%s)" % (cls.__name__, node.attrib.get("name"))
      raise

  @property
  def is_valid (self):
    return True

  def _init (self):
    # Called after properties set
    pass

  def __repr__ (self):
    kvs = {k:v for k,v in vars(self).items() if not k.startswith("_")}
    for k,v in kvs.items():
      if isinstance(v,list):
        v = "[..%s..]" % (len(v),)
      elif isinstance(v, GIRNode):
        v = "<%s>" % (type(v).__name__,)
      else:
        v = repr(v)
      kvs[k] = v
    if "name" in kvs:
      name = kvs.pop("name")
      kvs = kvs.items()
      kvs.insert(0, ("name",name))
    else:
      kvs = kvs.items()

    kv = " ".join("%s=%s" % (k,v) for k,v in kvs)
    if kv: kv = " " + kv
    return "<%s%s>" % (type(self).__name__, kv)


class Member (GIRNode):
  """
  Member of a bitfield or enum
  """
  pass

class Enumeration (GIRNode, ImportedType):
  AUTO_PARSE = {"member":[Member]}
  def _init (self):
    self.members = [(m.name, int(m.value),m.c__identifier) for m in self.member]
    self.members.sort(key=lambda x: x[1])

  def _new (self, n, native_v=None, v=None):
    assert native_v is not None or v is not None
    assert v is None
    if v is None: v = '(native("%s")->IntPtr)' % (native_v,)
    return "%s = %s(%s)" % (valid_name(n), self._rname, v)

  def _nread (self, n):
    return "(($%s).value)" % (valid_name(n),)

class Bitfield (Enumeration):
  pass


class Include (GIRNode):
  pass

class TypeRef (GIRNode):
  _type = None

  def resolve_type (self):
    if "." in self.name:
      t = find_type(self.name)
    else:
      ns = self._get_ancestor(Namespace)
      t = ns._types.get(self.name)
    self._type = t
    if not t:
      squelch(self.log.warn, "Can't resolve type %s", self.name)

class Constant (GIRNode):
  AUTO_PARSE = {"type":TypeRef}


class ArrayRef (GIRNode):
  _type = None
  length = int
  zero_terminated = False
  _PARSE_zero_terminated = Bool

  AUTO_PARSE = {"type":TypeRef}

  def resolve_type (self):
    if not hasattr(self, "name"):
      self.name = "array-of-" + self.type.name

    if not self.type._type:
      squelch(self.log.warn, "Can't resolve array of unresolved type %s", self.type.name)

    t = get_array_type_from_ref(self)
    self._type = t
    if not t:
      squelch(self.log.warn, "Can't resolve array of type %s", self.type.name)


class Alias (GIRNode):
  AUTO_PARSE = {"type":TypeRef}

  @property
  def is_valid (self):
    return self.type is not None


class ReturnValue (GIRNode):
  AUTO_PARSE = {"type":TypeRef, "array":ArrayRef}
  transfer_ownership = None




class Parameter (GIRNode):
  AUTO_PARSE = {"type":TypeRef, "array":ArrayRef}
  direction = None
  caller_allocates = False
  _PARSE_caller_allocates = Bool
  nullable = True
  _PARSE_nullable = Bool
  transfer_ownership = None
  optional = None
  allow_none = None



class Parameters (GIRNode):
  """
  Only used for parsing; Function immediately throws it away
  """
  # Note a potential issue here if instance-parameter isn't first, since we can't tell ordering
  AUTO_PARSE = {"parameter": [Parameter], "instance-parameter": Parameter}


class FunctionOrMethod (GIRNode):
  """
  Function, Method, or Constructor
  """
  _context = None
  AUTO_PARSE = {"return-value":ReturnValue, "parameters":Parameters}
  throws = False
  _PARSE_throws = Bool

  def _init (self):
    if self.parameters:
      p = self.parameters.parameter
      if self.parameters.instance_parameter:
        p = [self.parameters.instance_parameter] + p
      self.parameters = p
    else:
      self.parameters = []
    self._is_constructor = self.EL_NAME == "constructor"


class Field (GIRNode):
  private = False
  _PARSE_private = Bool
  introspectable = False
  _PARSE_introspectable = Bool



class Record (GIRNode, ImportedType):
  _is_reference = True # Is that always so?

  AUTO_PARSE = {"method":[FunctionOrMethod], "constructor":[FunctionOrMethod]}

  def _init (self):
    for m in self.method:
      m._context = self
    for m in self.constructor:
      m._context = self

  def find_method (self, n):
    for m in self.method:
      if m.name == n: return m
    return False

class Union (Record):
  pass

class Class (GIRNode, ImportedType): # Should this be a subclass of Record?
  _is_reference = True # Is that always so?
  _parent_type = None
  parent = None

  AUTO_PARSE = {"method":[FunctionOrMethod], "constructor":[FunctionOrMethod], ns_glib+"signal":[FunctionOrMethod]}

  def _init (self):
    for m in self.method:
      m._context = self
    for m in self.constructor:
      m._context = self

  def resolve_parent_type (self):
    if self.parent is None: return
    if "." in self.parent:
      t = find_type(self.parent)
    else:
      ns = self._get_ancestor(Namespace)
      t = ns._types.get(self.parent)
    self._parent_type = t
    if not t:
      squelch(self.log.warn, "Can't resolve parent %s for type %s", self.parent, self.name)

  def find_method (self, n):
    for m in self.method:
      if m.name == n: return m
    if self.parent:
      if hasattr(self.PARENT, 'find_method'):
        return self.PARENT.find_method(n)
    return False


class Namespace (GIRNode):
  AUTO_PARSE = {"union":[Union], "record":[Record], "constant":[Constant], "alias":[Alias], "bitfield":[Bitfield], "class":[Class], "function":[FunctionOrMethod], "enumeration":[Enumeration]}

  def _init (self):
    self._log = logging.getLogger(self.name)
    self._types = {} # name -> type_like

  def resolve_types (self):
    self._types.update(basic_types)
    def add_types (group):
      for x in group:
        n = x.name
        if n in self._types:
          raise RuntimeError("Type '%s' already exists (previous:%s new:%s)" % (n, self._types[n], x))
        self._types[n] = x
    add_types(self.cls)
    add_types(self.record)
    add_types(self.union)
    add_types(self.bitfield)
    add_types(self.enumeration)

  def resolve_aliases (self):
    for a in self.alias:
      t = a.type.name
      tt = self._types.get(t)
      if not tt:
        self.log.warn("Alias %s refers to unknown type %s" % (a.name, a.type.name))
      self._types[a.name] = tt





class Repository (GIRNode):
  AUTO_PARSE = {"include":[Include], "namespace":[Namespace]}





def augment (*args):
  if len(args) == 1:
    return do_augment(args[0], args[0].__name__)
  else:
    args = list(args)
    def x (cls):
      r = do_augment(cls, cls.__name__)
      if cls in args: args.remove(cls)
      for a in args:
        do_augment(cls, a.__name__)
      return r
    return x

def do_augment (cls, n):
  cls.__name__ += "AUGMENT"
  ocls = globals()[n]
  for k,v in vars(cls).items():
    if k.startswith("_"): continue
    setattr(ocls, k, v)
  return ocls


@augment
class TypeRef (object):
  def write_rogue (self, writer):
    print "WRITE ROGUE"


@augment
class Constant (object):
  def write_rogue (self, writer):
    if not self.type._type:
      self.log.warn("Skipping %s.%s (no type)", self._namespace_name, self.name)
      return
    if self.type._type.is_boolean:
      v = self.value
    elif self.type._type.is_numeric:
      v = float(self.value)
      if long(v) == v:
        v = long(v)
    else:
      # Assume it's a string?
      v = escape(self.value)

    writer.writeln("$define %s %s", self.name, v)

@augment(Enumeration,Bitfield)
class Enumeration (object):
  def write_rogue (self, writer):
    writer.writeln("enum %s # %s %s", self.name, self._get_ancestor(Namespace).name, type(self).__name__)
    writer.writeln("  CATEGORIES")
    for name,value,cid in self.members:
      if value >= 0x7fFFffFF: continue #FIXME
      writer.writeln("    %s = %s # %s", valid_name(name.upper()), value, cid) #m.c__identifier)
    writer.writeln("endEnum\n")

@augment(Class,Record,Union) # Class too
class Record (object):
  def write_rogue (self, writer):
    writer.write("class %s", self._rshort)
    parent = None
    if not hasattr(self, 'c__type'):
      self.log.error("Skipping class '%s' as it has no C type", self.name)
      writer.skip()
    ctype = self.c__type
    if getattr(self, "_parent_type", None):
      parent = getattr(self, "_parent_type")
      ctype = parent.c__type
      writer.write(" : %s", self._parent_type._rname)
    writer.writeln(" # %s %s", self._get_ancestor(Namespace).name, type(self).__name__)
    if not parent:
      writer.writeln("  PROPERTIES")
      writer.writeln('    native "%s * _self;"', self.c__type)
      writer.writeln("  METHODS")
      writer.writeln("    method _ptr_ () -> IntPtr")
      writer.writeln('      return native("$this->_self")->IntPtr')

    writer.writeln("  GLOBAL METHODS")
    writer.writeln("    method _create_ ( ptr: IntPtr, ref = false: Logical ) -> this")
    writer.writeln("      local r = <<%s>>.create_object<<%s>>()", self._rname, self._rname)
    #writer.writeln('      native "$r->_self = (%s *)$ptr; // _create_"', ctype)
    writer.writeln('      native "$r->_self = (%s *)$ptr; // _create_"', self._root_type.c__type) #XXX
    if self.find_method("ref"):
      writer.writeln("      if (ref) r.ref()")
    writer.writeln("      return r")
    writer.next()

    if self.method or self.constructor:
      with writer.indented(4):
        for i,m in enumerate(self.constructor):
          try:
            m.write_rogue(writer)
            writer.next()
          except SkipException:
            writer.writeln("# Skipped %s", m.name)
            writer.next()
      writer.writeln("  METHODS")
      writer.next()
      with writer.indented(4):
        for m in self.method:
          try:
            m.write_rogue(writer)
            writer.next()
          except SkipException as e:
            writer.writeln("# Skipped %s - %s", m.name, e.message or "<Unknown>")
            writer.next()
      with writer.indented(4):
        if hasattr(self, "glib__signal"):
          for m in self.glib__signal:
            try:
              m.write_rogue(writer)
              writer.next()
            except SkipException as e:
              writer.writeln("# Skipped %s - %s", m.name, e.message or "<Unknown>")
              writer.next()
      if self.find_method("unref"):
        with writer.indented(4):
          out.writeln("method on_cleanup\n  unref()\n  native @|$this->_self = NULL;")

    writer.writeln("endClass\n")

@augment
class Field (object):
  def write_rogue (self, writer):
    if self.private: writer.skip()
    if not self.introspectable: writer.skip()

    #TODO: Write something...


@augment
class FunctionOrMethod (object):
  def write_rogue (self, writer):
    is_signal = self.EL_NAME == ns_glib + "signal"

    if not self.name:
      self.log.warn("Skipping unnamed method of %s", self.name)
      writer.skip()

    fullname = self._get_ancestor(Namespace).name + "::"
    if self._context: fullname += self._context.name + "."
    fullname += self.name

    writer.writeln("# %s", fullname)

    if should_skip(fullname): writer.skip()


    rt = self.return_value.type or self.return_value.array
    rt_node = self.return_value
    if not rt._type:
      squelch(self.log.warn, "Skipping function/method because of bad return type %s" % (rt.name,))
      writer.skip("Bad return type")
    rt = rt._type
    if rt is VOID: rt = None

    if self._context or is_signal:
      writer.write("method ")
    else:
      writer.write("routine ")

    # Do some name-changing
    n = valid_name(self.name)
    as_ctor = False
    if self._is_constructor:
      def make_sig_part (p):
        pt = p.type # TODO: arrays  # or p.array
        if pt is None or pt._type is None: pt = str(id(self)) #FIXME: truly, truly, A++ horrible hack
        else: pt = pt._type._rname
        return pt
      as_ctor = True
      my_sig = "|".join(make_sig_part(x) for x in self.parameters)
      for c in self.PARENT.constructor:
        if c is self:
          # We made it here, so we're good.
          n = "create"
          break
        sig = "|".join(make_sig_part(x) for x in c.parameters)
        #if len(c.parameters) == len(self.parameters):
        if sig == my_sig:
          break
    elif is_signal:
      n = "connect_" + n
    elif n == "init":
      n = "_init"
    elif self._context and n == "equal":
      n = "operator=="

    writer.write(n + " (")
    if is_signal: writer.write("handler: (Function(")
    first = True
    for p in self.parameters:
      if p.EL_NAME == "instance-parameter": continue
      if not first: writer.write(", ")
      first = False
      t = p.type or p.array
      if not t or not t._type:
        if t is None: t = "<No type>"
        elif isinstance(t, TypeRef): t = t.name
        elif isinstance(t, ArrayRef): t = "<Array>"
        else: t = "<Unknown>"
        squelch(self.log.warn, "Skipping function/method because of bad parameter type %s" % (t,))
        writer.skip("Bad param type for %s (%s)" % (p.name,t))
      t = t._type
      alias = ""
      if p.direction == "out":
        if (is_signal): writer.skip("Out parameters are not supported for signals")
        if type(t) is DirectType:
          # Easy
          pass
#        elif isinstance(t, ImportedType):
#          #TODO: We should be able to handle these...
        else:
          squelch(self.log.warn, "Skipping method because out parameter was type '%s' which isn't an exact Rogue type" % (t.name,))
          writer.skip("Out param unsupported")
        alias = "@"
      if not is_signal: writer.write("%s: ", valid_name(p.name))
      writer.write("%s%s", t._rname, alias)
    writer.write(")")


    if as_ctor:
      writer.writeln("->this")
    elif rt:
      writer.write("->")
      writer.write(rt._rname)

    if is_signal: writer.write("), after=false:Logical)->IntPtr # SIGNAL")

    writer.writeln()

    throws = self.throws

    if is_signal:
      with writer.indented(2):
        writer.writeln("local _H_ = handler")
        writer.writeln("local handler_2 = function (args: GObject::Value[], rrv: GObject::Value) with (_H_)")
        with writer.indented(2):
          for i,p in enumerate(self.parameters):
            t = p.type or p.array
            if p.array:
              squelch(self.log.warn, "Skipping method because array parameters are not supported")
              writer.skip("Array param unsupported")
            t = t._type
            #TODO: Break this GValue conversion stuff into some convenient helpers...
            writer.writeln("local v%s = args[%s]", i, i)
            writer.writeln("native @|GValue * v%s = $v%s->_self;", i, i)
            writer.write("local a%s", i)
            if t.gval:
              writer.writeln(' = native("g_value_get_%s(v%s)")->%s', t.gval, i, t._rname)
            elif isinstance(t, Enumeration):
              writer.writeln(' = %s(native("g_value_get_enum(v%i)")->Int32)', t._rname, i)
            elif isinstance(t, Bitfield):
              writer.writeln(' = %s(native("g_value_get_flags(v%i)")->Int32)', t._rname, i)
            elif isinstance(t, Class):
              writer.writeln(' = %s._create_(native("g_value_get_object(v%i)")->IntPtr)', t._rname, i) #XXX ref?
            elif isinstance(t, (Record,Union)):
              writer.writeln(' = %s._create_(native("g_value_get_object(v%i)")->IntPtr)', t._rname, i) #XXX ref?  pointer, not object? boxed?
            elif isinstance(t, GStringType):
              writer.writeln(' = GI::GString._dup_(native("g_value_get_string(v%i)")->IntPtr)', i)
            else:
              writer.skip("Unsupported GValue parameter type")
          if rt:
            writer.write("local rv = ")
          writer.writeln("_H_(%s)", ", ".join("a" + str(x) for x in range(len(self.parameters))))
          if rt:
            writer.writeln('if (rrv and rrv._ptr_)')
            with writer.indented(2):
              writer.writeln('native "GValue * rv = (GValue *)$rrv->_self;"')
              if rt.gval:
                writer.writeln('native "g_value_set_%s(rv, (%s)$rv);"', rt.gval, rt.ctype)
              elif isinstance(rt, Enumeration):
                writer.writeln('native "g_value_set_enum(rv, (%s)$rv);"', "gint")
              elif isinstance(rt, Bitfield):
                writer.writeln('native "g_value_set_flags(rv, (%s)$rv);"', "guint")
              elif isinstance(rt, (Class,(Record,Union))): # ptr not obj for record?
                writer.writeln('native "g_value_set_object(rv, (gobject*)$rv->_self);"') #XXX take_object?
              elif isinstance(rt, GStringType):
                writer.writeln('native g_value_set_string(rv, $rv->_self);')
              else:
                writer.skip("Unsupported GValue return type")
            writer.writeln("endIf")

        writer.writeln("endFunction")
        writer.writeln('local r = GI::RogirBaseMarshaller.connect(this, "%s", handler_2, after)', self.name)
        writer.writeln('if (r == 0) throw ::Error("Signal did not connect")')
        writer.writeln('return r')

    else:
      with writer.indented(2):
        if throws: writer.writeln("local _err_ : IntPtr")
        for i,p in enumerate(self.parameters):
          if p.EL_NAME == "instance-parameter": continue
          pn = valid_name(p.name)
          t = p.type or p.array
          t = t._type
          if t._is_reference and not p.nullable:
            writer.writeln("require %s is not null", pn)
        with writer.native:
          for i,p in enumerate(self.parameters):
            t = p.type or p.array
            if p.array:
              squelch(self.log.warn, "Skipping method because array parameters are not supported")
              writer.skip("Array param unsupported")
            t = t._type
            if p.EL_NAME == "instance-parameter":
              r = "(%s)%s" % (p.type.c__type, t._nread("this"))
            else:
              r = t._nread(p.name)
            writer.writeln("%s a%s = (%s)%s;", p.type.c__type, i, p.type.c__type, r) #XXX Cast is new
          par = ["a" + str(x) for x in range(len(self.parameters))]
          if throws: par.append("(GError**)&$_err_")
          if rt:
            writer.write("auto rv1 = ")
          writer.writeln("%s(%s);", self.c__identifier, ", ".join(par))
          #writer.writeln("""native @|printf("returned\n");""")
          #TODO: Alias parameter read-backs
        if throws: writer.writeln("if (_err_) GI::RogirThrow(_err_)")

        if rt:
          if as_ctor:
            rt = self._context
          if rt._is_array:
            squelch(self.log.warn, "Skipping method because array return values are not supported")
            writer.skip("Array return val unsupported")
          if self.name == "ref": # and rt == self._context:
            writer.writeln("# %s %s", rt, self._context)
            #FIXME: This seems like such a hack; what's the clean solution?
            #       (we're ignoring a recursion issue)
            rt_node.transfer_ownership = "full"
          writer.writeln("local _rv_ : %s", rt._rname)
          writer.writeln(rt._new("_rv_", native_v="rv1"))
          if rt_node.transfer_ownership == None: rt_node.transfer_ownership = "full"

          if rt_node.transfer_ownership == "none":
            writer.writeln("# NONE")
            if isinstance(rt, (Record,Class,Union)):
              if rt.find_method("ref") and rt.find_method("unref"):
                x = rt.find_method("ref")
                xx = None
                if (x): xx = x._get_ancestor(Class)
                if xx: xx = xx.name

                writer.writeln("# %s %s %s", rt.name,x.name,xx)
                writer.writeln("_rv_.ref()")
          elif rt_node.transfer_ownership == "full":
            writer.writeln("# FULL")
            pass # No need to do anything
          else:
            writer.skip("Unknown ownership transfer")
          writer.write("return _rv_")
          writer.writeln()


    if not self._context and not is_signal:
      writer.writeln("endRoutine")



modules = {}





class Module (object):
  @classmethod
  def do_import (cls, name, version):
    if (name,version) in modules:
      return modules[(name,version)]
    else:
      m = cls(name, version)
      modules[(name,version)] = m
      m.order = len(modules) - 1
      m.do_imports()
      return m

  def __init__ (self, name, version):
    if isinstance(version, (int,float)): version = str(float(version))
    self.name = name
    self.version = version
    self.log = logging.getLogger(name)
    self.log.info("Importing %s %s", self.name, self.version)
    filename = os.path.join(src_dir, "%s-%s.gir" % (name, version))
    self.filename = filename
    self.tree = ET.parse(self.filename)
    self.root = self.tree.getroot()
    self.pkg = None
    p = self.root.find("package")
    if p is not None: self.pkg = p.attrib.get('name')
    if self.pkg is None:
      self.log.warn("No package name")
    self.c__include = []
    for x in self.root.findall(ns_c+"include"):
      self.c__include.append(x.attrib['name'])

    self.nses = []
    for n in self.root.findall("namespace"):
      self.nses.append(Namespace.parse(n, module=self))

  def do_imports (self):
    for inc in self.root.findall("include"):
      Module.do_import(**inc.attrib)

  def __str__ (self):
    return "<%s %s-%s>" % (type(self).__name__, self.name, self.version)





rogir_ns = Namespace()
rogir_ns.name = "Rogir"
rogir_ns._init()


def find_type (n):
  if not "." in n:
    return None
  ns,n = n.split(".",1)
  for x in Namespace.ALL:
    if x.name == ns:
      return x._types.get(n)
  return None


class RogirArrayType (RogirType):
  _is_array = True

def get_array_type_from_ref (a):
  rname = ""
  if a.zero_terminated: rname += "Z"
  rname += "ArrayOf" + a.type.name

  t = rogir_ns._types.get(rname)
  if t: return t

  t = RogirArrayType() #XXX
  t.name = rname
  t.__dict__['_rname'] = rname

  rogir_ns._types[rname] = t
  return t



class DirectType (RogirType):
  rtype = None
  gval = None

  @property
  def _rname (self):
    assert self.rtype is not None, self.name
    return self.rtype

  def __init__ (self, name, ctype, rtype=None, **kw):
    self.name = name
    self.ctype = ctype
    self.rtype = rtype
    for k,v in kw.items():
      assert hasattr(self, k), k
      setattr(self, k, v)

    if self.gval is True:
      assert self.name.startswith("g")
      self.gval = self.name[1:]

  def _nread (self, n): # Native read
    return "$" + valid_name(n)

  def _new (self, n, native_v=None, v=None):
    assert native_v is not None or v is not None
    if v is None: v = '(native("%s")->%s)' % (native_v, self._rname)
    return "%s = %s" % (valid_name(n), v)

class UnsignedType (DirectType):
  """
  Type for dealing with unsigned types

  Goes from a smaller unsigned integer on the C side to a larger signed
  integer on the Rogue side.
  """
  rtype = None

  def _nread (self, n): # Native read
    return "((%s)$%s)" % (self.ctype, valid_name(n))

  def _new (self, n, native_v=None, v=None):
    assert native_v is not None or v is not None
    if v is None: v = '(native("%s")->%s)' % (native_v, self._rname)
    #TODO: Do this right.
    return 'native "$%s = ($%s.type)(%s & 0xffFFffFFffFFffFF);"' % (valid_name(n), valid_name(n), native_v)

def add_basic_type (target, gtypes, ctype=True, rtype=None, **kw):
  if "is_numeric" not in kw: kw["is_numeric"] = True
  unsigned = kw.pop("unsigned", False)
  tc = UnsignedType if unsigned else DirectType
  if isinstance(gtypes, (set,list,tuple)):
    gtypes = list(gtypes)
  else:
    gtypes = [gtypes]
  if ctype is True: ctype = gtypes[0]
  t = tc(gtypes[0], ctype, rtype, **kw)
  for n in gtypes:
    assert n not in target
    target[n] = t

def add_basic_types (target):
  # Perfect matches
  add_basic_type(target, "gint", rtype="Int", gval=True)
  add_basic_type(target, "gint32", rtype="Int32", gval="int") # gval may be off
  add_basic_type(target, "gint64", rtype="Int64", gval=True)
  add_basic_type(target, "gint8", rtype="Int32", gval="schar")
  add_basic_type(target, "guint8", rtype="Byte", gval="uchar")
  add_basic_type(target, "gfloat", rtype="Real32", gval="float")
  add_basic_type(target, "gdouble", rtype="Real64", gval="double")

  # These aren't necessarily right on every platform.
  # Current ones are okay for x86-64
  add_basic_type(target, "glong", rtype="Int", gval=True) # ?
  add_basic_type(target, "gssize", rtype="Int64", gval="int64") # ? gval may be off

  # Sign problems
  add_basic_type(target, "guint", rtype="Int64", unsigned=True, gval=True) # Unsigned
  add_basic_type(target, "guint32", rtype="Int64", unsigned=True, gval="uint") # Unsigned, gval may be off
  add_basic_type(target, "guint64", rtype="Int64", gval=True) # Unsigned
  add_basic_type(target, "gchar", rtype="Int32", unsigned=True, gval="schar") # Wrong sign
  add_basic_type(target, "guint16", rtype="Int32", unsigned=True, gval="uint")

  # Misc
  add_basic_type(target, "gint16", rtype="Int32", unsigned=True, gval="int") #FIXME: Wrong size! Sign ok
  add_basic_type(target, "gboolean", rtype="Logical", is_numeric=False, is_boolean=True, gval=True)
  add_basic_type(target, "gulong", rtype="Int64", gval=True) # ? Unsigned
  add_basic_type(target, "gsize", rtype="Int64", gval="uint64") # ? Unsigned, gval may be off
  add_basic_type(target, "gpointer", rtype="IntPtr", gval=True)#, is_numeric=False)

  add_basic_type(target, "none", rtype="GVoid", is_numeric=False)

basic_types = {}
add_basic_types(basic_types)
VOID = basic_types['none']

class GStringType (ImportedType): # It isn't really!

  @property
  def _rname (self):
    return "GI::GString"

  _is_reference = True # Is that always so?
  def __init__ (self, name, ctype, rtype=None, **kw):
    self.name = name
    self.ctype = ctype
    self.rtype = rtype
    for k,v in kw.items():
      assert hasattr(self, k), k
      setattr(self, k, v)

  def _new (self, n, native_v=None, v=None):
    assert native_v is not None or v is not None
    assert v is None
    if v is None: v = '(native("(intptr_t)(%s)")->IntPtr)' % (native_v,)
    return "%s = %s._take_(%s)" % (valid_name(n), self._rname, v)

basic_types["utf8"] = GStringType("GString", "utf8", "GI::GString", is_numeric=False)

m = Module.do_import(sys.argv[1], sys.argv[2])
for next_m in modules.values():
  next_m.do_imports()


skip_list = set([
  "Json::Parser.load_from_stream",
  "Pango::Map",
  "Pango::IncludedModule",
])

def should_skip (full_name):
  if full_name in skip_list: return True
  return False

_kill = []
for cls in Class.ALL:
  if should_skip(cls._rname):
    _kill.append((cls._get_ancestor(Namespace),cls))
for cls in Record.ALL:
  if should_skip(cls._rname):
    _kill.append((cls._get_ancestor(Namespace),cls))
for cls in Union.ALL:
  if should_skip(cls._rname):
    _kill.append((cls._get_ancestor(Namespace),cls))

for n,k in _kill:
  if k in n.cls:
    type_log.error("Killed class %s", k._rname)
    n.cls.remove(k)
  elif k in n.record:
    type_log.error("Killed record %s", k._rname)
    n.record.remove(k)

for ns in Namespace.ALL:
  ns.resolve_types()
for ns in Namespace.ALL:
  ns.resolve_aliases()
for t in TypeRef.ALL:
  t.resolve_type()
for t in ArrayRef.ALL:
  t.resolve_type()
for t in Class.ALL:
  t.resolve_parent_type()


class SkipException (RuntimeError):
  pass


class Output (object):
  class Indented (object):
    def __init__ (self, parent, indent):
      if isinstance(indent, int):
        indent = " " * indent
      self.parent = parent
      self.indent = indent
    def __enter__ (self):
      self.parent._indent += self.indent
      return self.parent
    def __exit__ (self, type, value, traceback):
      if not self.parent._indent.endswith(self.indent):
        print "'%s' != '%s'" % (self.parent._indent, self.indent)
      assert self.parent._indent.endswith(self.indent)
      self.parent._indent = self.parent._indent[:-len(self.indent)]
      if isinstance(value, SkipException): return

  class NativeIndented (object):
    def __init__ (self, parent):
      self.parent = parent
    def __enter__ (self):
      self.parent._xindent += "native @|"
      self.parent._xnextindent += "        |"
      return self.parent
    def __exit__ (self, type, value, traceback):
      assert self.parent._indent.endswith("|")
      self.parent._indent = self.parent._indent[:-9]

  def __init__ (self, filename = None):
    self.filename = filename
    if filename is not None:
      self.f = file(filename, "w")
    else:
      self.f = sys.stdout
    self.buf = ''
    self._indent = ""
    self._hanging = True

  @property
  def _indent (self):
    return self._xindent
  @_indent.setter
  def _indent (self, v):
    self._xindent = v
    self._xnextindent = v

  def indented (self, indent):
    return self.Indented(self, indent)

  @property
  def native (self):
    return self.NativeIndented(self)

  def write (self, s, *args):
    if args: s = s % args
    if not s: return
    s = s.split("\n")
    if self._hanging:
      self.buf += self._indent
      self._xindent = self._xnextindent
      self._hanging = False
    self.buf += s[0]
    for x in s[1:]:
      if x:
        self.buf += "\n" + self._indent + x
        self._hanging = False
      else:
        self.buf += "\n"
        self._hanging = True

  def writeln (self, s="", *args):
    self.write(s + "\n", *args)

  def next (self):
    self.f.write(self.buf)
    self.buf = ''
    self._hanging = True

  def skip (self, msg=None):
    self.buf = ''
    self._hanging = True
    raise SkipException(msg)




out = Output(sys.argv[3])


log = logging.getLogger("writer")

def write_all (kind):
  if hasattr(kind, "ALL"): kind = kind.ALL
  for t in kind:
    try:
      t.write_rogue(out)
      out.next()
    except SkipException:
      pass
    except:
      log.exception("While writing " + str(t))

#out.writeln(file("rogir_header.rogue").read())
out.writeln('$include "rogir_header.rogue"')


for x in modules.values():
  for i in x.c__include:
    out.writeln('nativeHeader #include "%s"', i)

# Just use pkg-config for thse
#for ns in Namespace.ALL:
#  out.writeln('compileArg "-l%s"', ns.shared_library)

for ns in Namespace.ALL:
  out.writeln("module %s", ns.name)
  write_all(ns.constant)
  write_all(ns.enumeration)
  write_all(ns.bitfield)
  write_all(ns.function)

  write_all(ns.union)
  write_all(ns.record)
  write_all(ns.cls)
