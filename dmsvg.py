#!/usr/bin/env python3
"""
	dmsvg - Doom map SVG renderer
	by Revenant
	
	Scroll down for render settings.
	
	Copyright (c) 2020 Devin Acker

	Permission is hereby granted, free of charge, to any person obtaining a copy
	of this software and associated documentation files (the "Software"), to deal
	in the Software without restriction, including without limitation the rights
	to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
	copies of the Software, and to permit persons to whom the Software is
	furnished to do so, subject to the following conditions:

	The above copyright notice and this permission notice shall be included in
	all copies or substantial portions of the Software.

	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
	THE SOFTWARE.

"""

from omg import *
from sys import argv, stderr, exit
from PIL import Image
from xml.etree import ElementTree
from io import BytesIO
from base64 import b64encode
from argparse import ArgumentParser
from math import atan2, pi

class DrawMap():
	#
	# default parameters (these can be changed from the command line)
	#
	# size of border in map units
	border = 8
	# transparent background
	trans = False
	
	def __init__(self, wad, mapname):
		from struct import error as StructError
		try:
			self.edit = MapEditor(wad.maps[mapname])
		except StructError:
			raise ValueError("Hexen / ZDoom maps are not currently supported")
		
		self.xmin = min([ v.x for v in self.edit.vertexes])
		self.xmax = max([ v.x for v in self.edit.vertexes])
		self.ymin = min([-v.y for v in self.edit.vertexes])
		self.ymax = max([-v.y for v in self.edit.vertexes])
		
		width  = self.xmax - self.xmin + 2*self.border
		height = self.ymax - self.ymin + 2*self.border
		
		# normalize Y axis
		for v in self.edit.vertexes:
			v.y = -v.y
		
		# stash some useful line info for later
		for num, line in enumerate(self.edit.linedefs):
			vx_a = self.edit.vertexes[line.vx_a]
			vx_b = self.edit.vertexes[line.vx_b]
			
			line.id = num
			line.sector_front = self.edit.sidedefs[line.front].sector
			if line.two_sided:
				line.sector_back = self.edit.sidedefs[line.back].sector
			else:
				line.sector_back = -1
				
			line.point_top   = min(self.edit.vertexes[line.vx_a].y, self.edit.vertexes[line.vx_b].y)
			line.point_left  = min(self.edit.vertexes[line.vx_a].x, self.edit.vertexes[line.vx_b].x)
			line.point_right = max(self.edit.vertexes[line.vx_a].x, self.edit.vertexes[line.vx_b].x)
				
			# TODO: normalize vertices into same quadrant here?
			line.angle = atan2(vx_b.x - vx_a.x, vx_b.y - vx_a.y) % (2 * pi)
			
		#	print("line %d angle is %d" % (num, line.angle * 180 / pi))
		
		# initialize image
		self.svg = ElementTree.Element('svg')
		self.svg.attrib['xmlns'] = "http://www.w3.org/2000/svg"
		self.svg.attrib['viewBox'] = "%d %d %u %u" % (self.xmin - self.border, self.ymin - self.border, width, height)
	#	self.svg.attrib['stroke'] = "#fff"

		# define patterns for all flats in map
		defs = ElementTree.SubElement(self.svg, 'defs')
		floors = set([s.tx_floor for s in self.edit.sectors])
		for f in floors:
			try:
				img = wad.flats[f].to_Image()
				img_data = BytesIO()
				img.save(img_data, "png")
			except KeyError:
				continue
		
			pattern = ElementTree.SubElement(defs, 'pattern')
			pattern.attrib['id'] = f
			pattern.attrib['patternUnits'] = "userSpaceOnUse"
			pattern.attrib['width'] = str(img.width)
			pattern.attrib['height'] = str(img.height)
			
			image = ElementTree.SubElement(pattern, 'image')
			image.attrib['href'] = "data:image/png;base64," + str(b64encode(img_data.getvalue()), 'ascii')
			image.attrib['x'] = "0"
			image.attrib['y'] = "0"
			image.attrib['width'] = str(img.width)
			image.attrib['height'] = str(img.height)

		# brightness filters
		lights = set([s.light >> 3 for s in self.edit.sectors])
		for light in lights:
			filter = ElementTree.SubElement(defs, 'filter')
			filter.attrib['id'] = "light" + str(light)
			transfer = ElementTree.SubElement(filter, 'feComponentTransfer')
			funcR = ElementTree.SubElement(transfer, 'feFuncR')
			funcG = ElementTree.SubElement(transfer, 'feFuncG')
			funcB = ElementTree.SubElement(transfer, 'feFuncB')
			funcR.attrib['type'] = "linear"
			# a lighting curve that i basically pulled out of my ass
			funcR.attrib['slope'] = str(1.5 * (light/32)**2)
			funcG.attrib = funcR.attrib
			funcB.attrib = funcR.attrib

		# add opaque background if specified
		if not self.trans:
			bg = ElementTree.SubElement(self.svg, 'rect')
			bg.attrib['fill']   = "#fff"
			bg.attrib['stroke'] = "#fff"
			bg.attrib['x'] = str(self.xmin - self.border)
			bg.attrib['y'] = str(self.ymin - self.border)
			bg.attrib['width'] = str(width)
			bg.attrib['height'] = str(height)

	def draw_lines(self, lines, sector):
		if len(lines) < 2:
			return
	
		flat = None
		light = None
		if sector >= 0:
			try:
				flat = self.edit.sectors[sector].tx_floor
				light = self.edit.sectors[sector].light >> 3
			except IndexError:
				pass
		
		if lines[0].vx_a in (lines[1].vx_a, lines[1].vx_b):
			last_vx = self.edit.vertexes[lines[0].vx_b]
		else:
			last_vx = self.edit.vertexes[lines[0].vx_a]
		
		d = "M %d,%d " % (last_vx.x, last_vx.y)
		
		for line in lines:
			vx_a = self.edit.vertexes[line.vx_a]
			vx_b = self.edit.vertexes[line.vx_b]
			if last_vx == vx_a:
				d += "L %d,%d " % (vx_b.x, vx_b.y)
				last_vx = vx_b
			else:
				d += "L %d,%d " % (vx_a.x, vx_a.y)
				last_vx = vx_a
		d += "z"
		
		path = ElementTree.SubElement(self.svg, 'path')
		path.attrib['d'] = d
		if flat:
			path.attrib['fill'] = "url(#%s)" % flat
			if light:
				path.attrib['filter'] = "url(#light%d)" % light
		elif self.trans:
			path.attrib['fill'] = "rgba(0,0,0,0)"
		else:
			path.attrib['fill'] = "#fff"
	
	def linesort(self, line):
		# sort by the following, in order:
		# left-most vertex
		# top-most vertex
		# right-most vertex
		# angle
		return (line.point_left, line.point_top, -line.point_right, line.angle)
	
	def trace_lines(self, line, sector=None, visited=None):
		if visited is None:
			visited = []
		
		# how to get next line?
		use_front = False
		
		# first, which sector are we looking at?
		two_sided = line.two_sided
		if line.angle > 0 and line.angle <= pi:
			use_front = True
		
		sector = line.sector_front
		if line.two_sided and not use_front:
			sector = line.sector_back
	#	print("\nvisiting sector %u, use_front = %s" % (sector, use_front))
		
		last_vx = line.vx_b
		
		while True:
			visited.append(line)
			
			# find another line with other connected point, same sector
			next_lines = self.lines_at_vertex[sector][last_vx]
			next_lines = [other for other in next_lines if other not in visited]
		#	next_lines.sort(key = lambda other: abs(line.angle - other.angle))
		#	print("visiting line %d from (%d,%d) to (%d,%d)" % (line.id, self.edit.vertexes[line.vx_a].x, self.edit.vertexes[line.vx_a].y, self.edit.vertexes[line.vx_b].x, self.edit.vertexes[line.vx_b].y))
			
			if len(next_lines) == 0:
				break
			
			line = next_lines[0]
			last_vx = line.vx_a if last_vx == line.vx_b else line.vx_b
		
		if not two_sided and not use_front:
			# we used the front of this 1s line for finding adjacent lines,
			# but don't use it for rendering empty space
			sector = -1
		
		return visited, sector
	
	def save(self, filename):
		# group lines by sector and vertex for faster searching later
		self.lines_at_vertex = [{} for s in self.edit.sectors]
		self.lines_in_sector = [[] for s in self.edit.sectors]
		def addline_sv(sector, vertex, line):
			if vertex not in self.lines_at_vertex[sector]:
				self.lines_at_vertex[sector][vertex] = []
			self.lines_at_vertex[sector][vertex].append(line)
		
		def addline_s(sector, line):
			addline_sv(sector, line.vx_a, line)
			addline_sv(sector, line.vx_b, line)
			self.lines_in_sector[sector].append(line)
		
		def addline(line):
			if line.two_sided:
				if line.sector_front != line.sector_back:
					# ignore 2s lines w/ same sector on both sides
					addline_s(line.sector_front, line)
					addline_s(line.sector_back, line)
			else:
				addline_s(line.sector_front, line)
		
		for line in self.edit.linedefs:
			addline(line)
		
		for lines_left in self.lines_in_sector:
			lines_left.sort(key = self.linesort)
			while len(lines_left) > 0:
				try:
					visited, sector = self.trace_lines(lines_left[0])
					self.draw_lines(visited, sector)
					for line in visited:
						if line in lines_left:
							lines_left.remove(line)
							
				except KeyboardInterrupt:
					print("\nRendering canceled.")
					exit(-1)
				
		ElementTree.ElementTree(self.svg).write(filename)
		print("Rendered %s." % filename)

def get_args():
	ap = ArgumentParser()
	ap.add_argument("filename", help="path to WAD file")
	ap.add_argument("map",      help="name of map (ex. MAP01, E1M1)")
	
	ap.add_argument("-b", "--border", type=int, default=DrawMap.border,
	                help="size of border (default: %(default)s)")
	ap.add_argument("-t", "--trans", action="store_true",
	                help="make image background transparent")

	if len(argv) < 3:
		ap.print_help()
		exit(-1)
	
	args = ap.parse_args()
	
	# apply optional arguments to DrawMap settings
	DrawMap.border       = args.border
	DrawMap.trans        = args.trans
	
	return args
	
if __name__ == "__main__":
	print("dmsvg - Doom map SVG renderer")
	print("by Devin Acker (Revenant), 2020\n")
	
	args = get_args()
	
	filename = args.filename
	mapname  = args.map.upper()
	
	wad = WAD()
	
	# quick hack to support non-standard map names in omgifol 0.2
	# (not required with my fork)
	try:
		omg.wad._mapheaders.append(mapname)
	except AttributeError:
		pass
	
	try:
		wad.from_file(filename)
		
	except AssertionError:
		stderr.write("Error: Unable to load WAD file.\n")
		exit(-1)
	
	if mapname not in wad.maps:
		stderr.write("Error: Map %s not found in WAD.\n" % mapname)
		exit(-1)
	
	try:
		draw = DrawMap(wad, mapname)
		draw.save("%s_%s.svg" % (filename, mapname))
	except ValueError as e:
		stderr.write("Error: %s.\n" % e)
		exit(-1)
	