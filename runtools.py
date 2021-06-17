# Written by Pavlo Pastaryev

import os
import subprocess
import argparse
import sys

from os import listdir
from os.path import isfile, join

# run a shell process and get its stdout and sterr
def run_command(cmd):
	process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	stdout, stderr = process.communicate()
	return (stdout.decode('ascii'), stderr.decode('ascii'))

# find an error file with the specified error and return its path
def klee_find_err_file(error):
	klee_files = [f for f in listdir('klee-last/') if isfile(join('klee-last/', f))]
	for f in klee_files:
		if f.endswith('.err'):
			error_file_dump = open('klee-last/'+f, 'r').read()
			if error in error_file_dump:
				return 'klee-last/'+f
	return ''

# get the input of a desired test case using ktest-tool
def klee_get_test(ktool_path, test_file, objects):
	test_out = run_command([ktool_path, test_file])
	if 'ERROR' in test_out[0]:
		print('\033[1;31;40m\033[1;31;48m[~] ktest-tool error, dumping output')
		print('\033[1;37;48m'+test_out[0])
		return None

	parsed_objects = []
	for o in objects:
		for line in test_out[0].split('\n'):
			if 'object ' + str(o) in line and 'name' in line:
				obj_name = line.split(' ')[-1][1:-1]
				parsed_objects.append([obj_name])
				print('\033[1;37;48m'+obj_name + ':')
				continue
			if 'object ' + str(o) in line and 'hex' in line:
				obj_val = line.split(' ')[-1]
				parsed_objects[-1].append(obj_val)
				print('\033[1;37;48m'+obj_val)
				break

	return parsed_objects

# change the source file to be operable by another tool, e.g. ikos instead of klee
# works based on comments in the source file
def rewrite_source(source, comment, uncomment):
	lines = ''
	with open(source, 'r') as f:
		init_lines = f.readlines()
		for line in init_lines:
			if '// ' + comment in line and '// ' + uncomment in line:
				lines += line
			elif '// ' + comment in line:
				lines += '//' + line
			elif '// ' + uncomment in line:
				lines += line[2:]
			else:
				lines += line
	with open(source, 'w') as f:
		f.write(lines)

# fill in the test case that was previously retrieved
# used with ikos
def fill_test(source, test, fill):
	lines = ''
	with open(source, 'r') as f:
		lines = f.read()
		if fill:
			for t in test:
				lines = lines.replace('$'+t[0], t[1][2:])
		else:
			for t in test:
				lines = lines.replace(t[1][2:], '$'+t[0])
	with open(source, 'w') as f:
		f.write(lines)

# run klee on the source file
def run_klee(source_file, clang_path, ktool_path, klee_path, objects, error):
	print('\033[1;33;48m\033[1;33;48m[~] Compiling source with clang')
	clang_out = run_command([clang_path, '-emit-llvm', '-c', source_file])
	if clang_out[1] != '':
		print('\033[1;31;48m\033[1;31;48m[-] Clang error, dumping output:')
		print('\033[1;37;48m'+clang_out[1])
		return 0, None
	print('\033[1;32;48m\033[1;32;48m[+] Success\n')

	print('\033[1;33;48m[~] Running KLEE')
	klee_out = run_command([klee_path, source_file[:-1] + 'bc'])
	if error not in klee_out[1]:
		print('\033[1;31;48m[-] KLEE did not find the specified error\n')
		return 0, None
	
	print('\033[1;32;48m[+] Successfully found error ' + error + ' in KLEE output')
	klee_err_file = klee_find_err_file(error)
	if klee_err_file == '':
		print('\033[1;31;48m[-] Could not find error dump in klee-last directory')
		return 0, None
	
	print('\033[1;33;48m[~] The error dump is located in ' + klee_err_file)
	print('\033[1;33;48m[~] Getting test case')
	test = klee_get_test(ktool_path, klee_err_file.split('.')[0] + '.ktest', objects)
	if test is None:
		print('\033[1;31;48m[-] No test case found')
		return 0, None
	
	print()
	return 1, test

# run ikos on the source file
def run_ikos(source_file, ikos_path, test, error):
	print('\033[1;33;48m[~] Running ikos')
	ikos_out = run_command([ikos_path, source_file])
	if 'error' in ikos_out[1]:
		print('\033[1;31;48m[-] Error when running IKOS, dumping output')
		print('\033[1;37;48m'+'\n'.join(ikos_out[1].split('\n')))
		return 0
	if error not in ikos_out[0]:
		print('\033[1;31;48m[-] IKOS was not able to find ' + error + ' error, dumping output')
		print('\033[1;37;48m'+'\n'.join(ikos_out[0].split('\n')))
		return 0

	print('\033[1;32;48m[+] Successfully found error ' + error + ' in IKOS output')
	ikos_lines = ikos_out[0].split('\n')
	for i in range(len(ikos_lines)):
		if error in ikos_lines[i]:
			print('\033[1;37;48m'+ikos_lines[i-2])
			print('\033[1;37;48m'+ikos_lines[i-1])
			print('\033[1;37;48m'+ikos_lines[i])
			print()
	return 1

# run cbmc on the source file
def run_cbmc(source_file, cbmc_path):
	print('\033[1;33;48m[~] Running CBMC')
	cbmc_out = run_command([cbmc_path, source_file])
	if 'error' in cbmc_out[1]:
		print('\033[1;31;48m[-] Error when running CBMC, dumping output')
		print('\033[1;37;48m'+cbmc_out[1])
		rewrite_source(source_file, 'cbmc', 'klee')
		return 0
	if 'FAILURE' not in cbmc_out[0]:
		print('\033[1;31;48m[-] CBMC found no errors\n')
		return 0

	print('\033[1;32;48m[+] Found the following errors:')
	for line in cbmc_out[0].split('\n'):
		if 'FAILURE' in line:
			print('\033[1;37;48m'+line)
	print()
	return 1

# run klee, ikos and cbmc on the source file
def run_tools(source_file, clang_path, klee_path, ktool_path, objects, cbmc_path, ikos_path, error):
	successes, test = run_klee(source_file, clang_path, ktool_path, klee_path, objects, error)

	print('\033[1;33;48m[~] Rewriting source file to use IKOS')
	rewrite_source(source_file, 'klee', 'ikos')
	if successes == 1:
		fill_test(source_file, test, True)
	print('\033[1;32;48m[+] Done\n')

	if successes == 1:
		successes += run_ikos(source_file, ikos_path, test, error)
	else:
		print('\033[1;31;48m[-] No test case generated by KLEE, skipping IKOS\n')

	print('\033[1;33;48m[~] Rewriting source file to use CBMC')
	rewrite_source(source_file, 'ikos', 'cbmc')
	if test is not None:
		fill_test(source_file, test, False)
	print('\033[1;32;48m[+] Done')
	print()

	successes += run_cbmc(source_file, cbmc_path)

	print('\033[1;32;48m[+] Number of tools that detected the error: ' + str(successes) + '/3')

	rewrite_source(source_file, 'cbmc', 'klee')

if __name__ == '__main__':
	parser = argparse.ArgumentParser(prog=sys.argv[0], description = 'Run klee, ikos and cbmc on a c source file.')
	parser.add_argument('-s', dest = 'source_file', default = 'ntlm.c')
	parser.add_argument('-e', dest = 'error', default = 'memcpy')
	parser.add_argument('--clang', dest = 'clang_path', default = 'clang')
	parser.add_argument('--klee', dest = 'klee_path', default = 'klee')
	parser.add_argument('--ktest-tool', dest = 'ktool_path', default = 'ktest-tool')
	parser.add_argument('-o', dest = 'objects', type=str, default='0', help='List comma-separated of klee symbolic objects')
	parser.add_argument('--ikos', dest = 'ikos_path', default='ikos')
	parser.add_argument('--cbmc', dest = 'cbmc_path', default='cbmc')

	args = parser.parse_args()

	run_tools(args.source_file, args.clang_path, args.klee_path, args.ktool_path, args.objects.split(','), args.cbmc_path, args.ikos_path, args.error)