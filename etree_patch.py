# Gross monkey patching of etree.  We should just get rid of it.  Then
# we can use lxml which may be quite a bit faster.

import xml.etree.ElementTree as ET

def patch_et (nsmap):
  def new_find (*args, **kw):
    args = list(args)
    obj = args[0]
    args = args[1:]
    ns = nsmap
    if len(args) == 1:
      args.append(nsmap)
    elif 'nsmap' not in kw:
      kw['nsmap'] = nsmap
    else:
      ns = args[1] if len(args) > 1 else kw.get("nsmap",{})
    if ":" not in args[0] and not args[0].startswith("{"):
      if None in ns:
        args[0] = "{%s}%s" % (ns[None], args[0])
    return old_find(obj, *args, **kw)
  old_find = ET.Element.find
  ET.Element.find = new_find

  def new_findall (*args, **kw):
    args = list(args)
    obj = args[0]
    args = args[1:]
    ns = nsmap
    if len(args) == 1:
      args.append(nsmap)
    elif 'nsmap' not in kw:
      kw['nsmap'] = nsmap
    else:
      ns = args[1] if len(args) > 1 else kw.get("nsmap",{})
    if ":" not in args[0] and not args[0].startswith("{"):
      if None in ns:
        args[0] = "{%s}%s" % (ns[None], args[0])
    return old_findall(obj, *args, **kw)
  old_findall = ET.Element.findall
  ET.Element.findall = new_findall
